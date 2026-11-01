"""The web server.

A simulated day is deterministic, so the server computes the whole day when asked (about half a second for a
ten-minute day) and then plays it back at whatever speed the viewer wants. Playing back a finished, fingerprinted
run is indistinguishable from watching it live, and it lets a viewer drag backwards to any earlier moment.

    POST /api/runs                  start (compute) a day; the same settings give the same run id
    GET  /api/runs/{id}             summary: settings, instrument, event count, fingerprint
    GET  /api/runs/{id}/events      events as JSON, paged with ?start= and ?limit=
    GET  /api/runs/{id}/ends        the points where one command finishes (safe places to stop and look)
    GET  /api/runs/{id}/state       the market after the last full command at or before ?at= events
    WS   /ws/runs/{id}              events played back, one command at a time

WebSocket messages from the server: {"type":"hello", run}, {"type":"batch", events, upto, sim_time}, {"type":"done"}.
Messages from the client: {"type":"speed","value":10}, {"type":"pause"}, {"type":"resume"}.

The server only reads and plays back. Nobody can send an order in Week 5, and there is no login: run it on your own
computer (it listens on 127.0.0.1 by default).
"""

from __future__ import annotations

import asyncio
import bisect
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from marketlab.codec import event_to_dict
from marketlab.core import Instrument, Side
from marketlab.projection import MarketState
from marketlab.sim import SimConfig, SimulationResult, run_simulation

MAX_RUNS_KEPT = 16
MAX_PAGE = 20_000
MICROS = 1_000_000


class RunRequest(BaseModel):
    seed: int = Field(default=1, ge=0, le=2**32 - 1)
    open_seconds: int = Field(default=600, ge=10, le=3600)
    pre_open_seconds: int = Field(default=60, ge=5, le=600)
    noise_traders: int = Field(default=20, ge=0, le=100)


@dataclass
class StoredRun:
    id: str
    result: SimulationResult


class RunStore:
    """The most recent runs, in memory. Old ones are dropped; they can always be recomputed from their settings."""

    def __init__(self, limit: int = MAX_RUNS_KEPT) -> None:
        self._runs: OrderedDict[str, StoredRun] = OrderedDict()
        self._limit = limit

    def add(self, result: SimulationResult) -> StoredRun:
        run_id = result.sha256[:12]
        stored = self._runs.pop(run_id, None) or StoredRun(run_id, result)
        self._runs[run_id] = stored
        while len(self._runs) > self._limit:
            self._runs.popitem(last=False)
        return stored

    def get(self, run_id: str) -> StoredRun | None:
        stored = self._runs.get(run_id)
        if stored is not None:
            self._runs.move_to_end(run_id)
        return stored


def instrument_json(instrument: Instrument) -> dict[str, Any]:
    return {
        "symbol": instrument.symbol,
        "tick_size": instrument.tick_size,
        "lot_size": instrument.lot_size,
        "reference_price": instrument.reference_price,
        "band_low": instrument.band_low,
        "band_high": instrument.band_high,
    }


def summary(run: StoredRun) -> dict[str, Any]:
    result = run.result
    return {
        "id": run.id,
        "config": result.config.to_dict(),
        "instrument": instrument_json(result.instrument),
        "events": len(result.events),
        "commands": len(result.ends),
        "sha256": result.sha256,
        "duration_us": result.events[-1].sim_time if result.events else 0,
    }


def state_json(state: MarketState, levels: int | None = None) -> dict[str, Any]:
    """The market as plain data. The dashboard's own copy of the fold must produce exactly this."""

    def side(which: Side) -> list[dict[str, Any]]:
        return [
            {
                "price": view.price,
                "quantity": view.quantity,
                "orders": [
                    {"id": order_id, "account": state.orders[order_id].account_id, "remaining": left}
                    for order_id, left in state.queue(which, view.price)
                ],
            }
            for view in state.depth(which, levels)
        ]

    return {
        "at": state.events_applied,
        "session": state.session.value,
        "opening_price": state.opening_price,
        "last_price": state.last_price,
        "high": state.high,
        "low": state.low,
        "trades": state.trades,
        "volume": state.volume,
        "best_bid": state.best_bid(),
        "best_ask": state.best_ask(),
        "pending_market": [[order_id, left] for order_id, left in sorted(state.pending_market.items())],
        "bids": side(Side.BUY),
        "asks": side(Side.SELL),
    }


def snapshot(run: StoredRun, at: int, levels: int) -> dict[str, Any]:
    """The market after the last finished command at or before `at` events."""
    ends = run.result.ends
    position = bisect.bisect_right(ends, at)
    count = ends[position - 1] if position else 0
    state = MarketState(run.result.instrument)
    state.apply_all(run.result.events[:count])
    return state_json(state, levels)


class _Control:
    """What the viewer has asked for while the stream is playing."""

    def __init__(self, speed: float) -> None:
        self.speed = speed
        self.paused = False

    def handle(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "pause":
            self.paused = True
        elif kind == "resume":
            self.paused = False
        elif kind == "speed":
            value = message.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool) and 0.1 <= value <= 1_000_000:
                self.speed = float(value)


def create_app(web_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="Market Lab", version="0.5.0")
    store = RunStore()

    def find(run_id: str) -> StoredRun:
        run = store.get(run_id)
        if run is None:
            raise HTTPException(404, "unknown run: start one with POST /api/runs (runs are kept in memory)")
        return run

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/runs")
    def start_run(request: RunRequest | None = None) -> dict[str, Any]:
        request = request or RunRequest.model_validate({})
        config = SimConfig(
            seed=request.seed,
            open_seconds=request.open_seconds,
            pre_open_seconds=request.pre_open_seconds,
            noise_traders=request.noise_traders,
        )
        return summary(store.add(run_simulation(config)))

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        return summary(find(run_id))

    @app.get("/api/runs/{run_id}/events")
    def get_events(
        run_id: str, start: int = Query(0, ge=0), limit: int = Query(1000, ge=1, le=MAX_PAGE)
    ) -> dict[str, Any]:
        events = find(run_id).result.events
        page = events[start : start + limit]
        return {"total": len(events), "start": start, "events": [event_to_dict(e) for e in page]}

    @app.get("/api/runs/{run_id}/ends")
    def get_ends(run_id: str) -> dict[str, Any]:
        return {"ends": find(run_id).result.ends}

    @app.get("/api/runs/{run_id}/state")
    def get_state(run_id: str, at: int = Query(..., ge=0), levels: int = Query(10, ge=1, le=100)) -> dict[str, Any]:
        return snapshot(find(run_id), at, levels)

    @app.websocket("/ws/runs/{run_id}")
    async def stream(websocket: WebSocket, run_id: str, speed: float = 10.0, start: int = 0) -> None:
        await websocket.accept()
        run = store.get(run_id)
        if run is None:
            await websocket.close(code=4404, reason="unknown run")
            return
        control = _Control(min(max(speed, 0.1), 1_000_000))
        listener = asyncio.create_task(_listen(websocket, control))
        try:
            await websocket.send_json({"type": "hello", "run": summary(run)})
            await _play(websocket, run, control, start, listener)
            if not listener.done():
                await websocket.send_json({"type": "done"})
        except WebSocketDisconnect:
            pass
        finally:
            listener.cancel()
        try:
            await websocket.close()
        except RuntimeError:  # already closed by the other side
            pass

    if web_dir is not None and web_dir.is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app


async def _listen(websocket: WebSocket, control: _Control) -> None:
    try:
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict):
                control.handle(message)
    except (WebSocketDisconnect, RuntimeError, ValueError):
        return


async def _play(
    websocket: WebSocket, run: StoredRun, control: _Control, start: int, listener: asyncio.Task[None]
) -> None:
    events = run.result.events
    previous_end, previous_time = 0, 0
    for end in run.result.ends:
        if listener.done():
            return
        batch = events[previous_end:end]
        now = batch[-1].sim_time
        if end > start:
            waited = 0.0
            wanted = (now - previous_time) / MICROS
            while not listener.done():
                if control.paused:
                    await asyncio.sleep(0.05)
                    continue
                remaining = wanted - waited * control.speed
                if remaining <= 0:
                    break
                step = min(0.1, remaining / control.speed)
                await asyncio.sleep(step)
                waited += step
        await websocket.send_json(
            {"type": "batch", "events": [event_to_dict(e) for e in batch], "upto": end, "sim_time": now}
        )
        previous_end, previous_time = end, now
