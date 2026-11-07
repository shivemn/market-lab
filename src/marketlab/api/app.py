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

Practice sessions (Week 9). The server owns no clock: the day moves only when the browser asks it to.

    POST   /api/sessions                       start a day for a practice account; returns the opening events
    GET    /api/sessions/{id}                  the account: cash, set aside, shares, open orders
    GET    /api/sessions/{id}/market           the market as it stands now
    GET    /api/sessions/{id}/statement        every trade and charge so far, and what trading has cost
    POST   /api/sessions/{id}/advance          move the day forward {seconds}; stops early when your order trades
    POST   /api/sessions/{id}/orders           place an order; a refusal is a 422 with the reason in plain words
    DELETE /api/sessions/{id}/orders/{order}   cancel an open order
    DELETE /api/sessions/{id}                  leave the day early; money set aside is returned

Practice worlds (twelve companies on one clock, with indices). Same rules as a session: the browser owns the clock.

    POST   /api/worlds                          start a day in all twelve companies; returns the opening events
    GET    /api/worlds/{id}/statement           every trade and charge, and how each company has done for you
    POST   /api/worlds/{id}/advance             move the day forward {seconds}; stops early when your order trades
    POST   /api/worlds/{id}/orders              place an order in one company {symbol, side, quantity, ...}
    DELETE /api/worlds/{id}/orders/{symbol}/{order}    cancel an open order
    DELETE /api/worlds/{id}                     leave the day early; money set aside is returned

There is no login. Run it on your own computer (it listens on 127.0.0.1 by default). Practice accounts live in a
SQLite file (`--db`), so cash and shares carry over from one day to the next.
"""

from __future__ import annotations

import asyncio
import bisect
import re
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from marketlab import accounts as auth
from marketlab.codec import event_to_dict
from marketlab.core import Instrument, Side, TimeInForce
from marketlab.costs import PLANS
from marketlab.ledger import Ledger, OrderRefused, build_statement
from marketlab.projection import MarketState
from marketlab.session import Portfolio, PracticeSession
from marketlab.sim import SimConfig, SimulationResult, run_simulation
from marketlab.world import (
    BY_SYMBOL,
    CATALOGUE,
    INDEX_NAME,
    SECTORS,
    PracticeWorld,
    WorldConfig,
    WorldPortfolio,
)

MAX_RUNS_KEPT = 16
MAX_SESSIONS_KEPT = 8
MAX_WORLDS_KEPT = 500  # a safety limit on live days held in memory; the least recently used one goes first
IDLE_SECONDS = 30 * 60  # a day nobody has touched for this long is saved to history and let go
_now = time.monotonic  # a name of its own so a test can move the clock
MAX_PAGE = 20_000
MICROS = 1_000_000


class RunRequest(BaseModel):
    seed: int = Field(default=1, ge=0, le=2**32 - 1)
    open_seconds: int = Field(default=600, ge=10, le=3600)
    pre_open_seconds: int = Field(default=60, ge=5, le=600)
    noise_traders: int = Field(default=20, ge=0, le=100)
    company: str | None = Field(default=None, pattern=r"^[A-Z0-9]{1,12}$", description="a symbol from the catalogue")


class SessionRequest(BaseModel):
    seed: int = Field(default=1, ge=0, le=2**32 - 1)
    open_seconds: int = Field(default=600, ge=10, le=3600)
    pre_open_seconds: int = Field(default=60, ge=5, le=600)
    noise_traders: int = Field(default=20, ge=0, le=100)
    owner: str = Field(default="you", pattern=r"^[A-Za-z0-9_-]{1,32}$")
    plan: Literal["zero", "flat20"] = "zero"
    trading_date: date | None = None


class AdvanceRequest(BaseModel):
    seconds: float = Field(ge=0, le=3600)
    pause_on_fill: bool = True


class OrderRequest(BaseModel):
    side: Literal["BUY", "SELL"]
    quantity: int = Field(ge=1, le=1_000_000)
    limit_price: int | None = Field(default=None, ge=1, description="paise; leave out for a market order")
    tif: Literal["DAY", "IOC"] = "DAY"


class WorldRequest(BaseModel):
    seed: int = Field(default=1, ge=0, le=2**32 - 1)
    open_seconds: int = Field(default=600, ge=10, le=3600)
    pre_open_seconds: int = Field(default=60, ge=5, le=600)
    owner: str = Field(default="you", pattern=r"^[A-Za-z0-9_-]{1,32}$")
    plan: Literal["zero", "flat20"] = "zero"
    trading_date: date | None = None
    fresh_prices: bool = Field(default=False, description="open at the starting prices, not yesterday's closes")


class EnterRequest(BaseModel):
    username: str = Field(max_length=64)
    secret: str = Field(max_length=200)
    create: bool = Field(default=False, description="yes, make a new account if this username is free")


class WorldOrderRequest(OrderRequest):
    symbol: str = Field(pattern=r"^[A-Z0-9]{1,12}$")


@dataclass
class StoredRun:
    id: str
    result: SimulationResult


class LedgerAttempts:
    """Attempt counts kept in the database, taking the server's lock around each use."""

    def __init__(self, ledger: Ledger, lock: threading.Lock) -> None:
        self._ledger = ledger
        self._lock = lock

    def recent(self, key: str, since: float) -> list[float]:
        with self._lock:
            return self._ledger.attempts_since(key, since)

    def add(self, key: str, at: float) -> None:
        with self._lock:
            self._ledger.add_attempt(key, at)

    def clear(self, key: str) -> None:
        with self._lock:
            self._ledger.clear_attempts(key)


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


def statement_json(session: PracticeSession) -> dict[str, Any]:
    """The account statement, with holdings valued at the last traded price (or the previous close before any trade)."""
    statement = build_statement(session.ledger, session.owner)
    symbol = session.sim.instrument.symbol
    price = session.sim.state.last_price or session.sim.instrument.reference_price
    result = statement.result({symbol: price})
    return {
        "symbol": symbol,
        "price": price,
        "rows": [
            {
                "at": r.at,
                "kind": r.kind,
                "memo": r.memo,
                "symbol": r.symbol,
                "shares_change": r.shares_change,
                "value": r.value,
                "charges": {line: amount for line, amount in r.charges},
                "money_change": r.money_change,
                "money_after": r.money_after,
            }
            for r in statement.rows
        ],
        "starting_money": statement.starting_money,
        "money": statement.money,
        "holdings": dict(statement.holdings),
        "bought": statement.bought,
        "sold": statement.sold,
        "traded_value": statement.traded_value,
        "charges_by_line": statement.charges_by_line,
        "total_charges": statement.total_charges,
        "charges_basis_points": statement.charges_basis_points,
        "worth": statement.worth({symbol: price}),
        "gain": result["gain"],
        "gain_before_charges": result["gain_before_charges"],
        "problems": statement.check() + session.ledger.verify(),
    }


def portfolio_json(folio: Portfolio) -> dict[str, Any]:
    return {
        "cash": folio.cash,
        "reserved": folio.reserved,
        "shares": folio.shares,
        "locked": folio.locked,
        "open_orders": [
            {
                "id": o.order_id,
                "side": o.side.value,
                "quantity": o.quantity,
                "remaining": o.remaining,
                "limit_price": o.limit_price,
            }
            for o in folio.open_orders
        ],
    }


def world_portfolio_json(folio: WorldPortfolio) -> dict[str, Any]:
    return {
        "cash": folio.cash,
        "reserved": folio.reserved,
        "holdings": {s: {"shares": h.shares, "locked": h.locked} for s, h in folio.holdings.items()},
        "open_orders": [
            {
                "symbol": o.symbol,
                "id": o.order_id,
                "side": o.side.value,
                "quantity": o.quantity,
                "remaining": o.remaining,
                "limit_price": o.limit_price,
            }
            for o in folio.open_orders
        ],
    }


def world_json(world_id: str, pw: PracticeWorld) -> dict[str, Any]:
    world = pw.world
    statement = pw.statement()  # built once: every part of the snapshot is worked out from this one reading
    prices = world.prices()
    positions = pw.positions(prices, statement)
    today = pw.today(positions)
    return {
        "id": world_id,
        "owner": pw.owner,
        "config": {
            "seed": pw.config.seed,
            "pre_open_seconds": pw.config.pre_open_seconds,
            "open_seconds": pw.config.open_seconds,
        },
        "index_name": INDEX_NAME,
        "sectors": [{"key": key, "label": label} for key, label in SECTORS],
        "companies": [
            {
                "symbol": c.symbol,
                "name": c.name,
                "sector": c.sector,
                "free_float_shares": c.free_float_shares,
                "instrument": instrument_json(world.sims[c.symbol].instrument),
            }
            for c in CATALOGUE
        ],
        "now": world.now,
        "open_at": world.open_at,
        "close_at": world.close_at,
        "finished": world.finished,
        "news": pw.news_view(),
        "benchmarks": pw.benchmarks_view(),
        "portfolio": world_portfolio_json(pw.portfolio()),
        "prices": prices,
        "indices": pw.indices(prices),
        "worth": statement.money + sum(q * prices[s] for s, q in statement.holdings if s in prices),
        "event_counts": {s: len(sim.events) for s, sim in world.sims.items()},
        "starting_money": statement.starting_money,
        "total_charges": statement.total_charges,
        "positions": {
            s: {
                "shares": p.shares,
                "average_cost": p.average_cost,
                "bought": p.bought,
                "sold": p.sold,
                "charges": p.charges,
                "realised": p.realised,
                "unrealised": p.unrealised,
                "net": p.net,
                "today": today[s],
            }
            for s, p in positions.items()
        },
    }


def ends_after(session: PracticeSession, events_before: int) -> list[int]:
    """The command boundaries (event counts) that came after the client's last event, so it can fold whole commands."""
    return [end for end in session.sim.ends if end > events_before]


def session_json(session_id: str, session: PracticeSession) -> dict[str, Any]:
    return {
        "id": session_id,
        "owner": session.owner,
        "config": session.config.to_dict(),
        "instrument": instrument_json(session.sim.instrument),
        "now": session.now,
        "open_at": session.sim.open_at,
        "close_at": session.sim.close_at,
        "finished": session.finished,
        "events": len(session.sim.events),
        "portfolio": portfolio_json(session.portfolio()),
    }


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


TOKEN_DAYS = 30
TAKEN_OR_WRONG = "That username is taken, or the secret is wrong."


def create_app(web_dir: Path | None = None, db_path: str = ":memory:", *, require_login: bool = False) -> FastAPI:
    app = FastAPI(title="Market Lab", version="0.9.0")
    store = RunStore()
    ledger = Ledger(db_path, shared_across_threads=True)
    sessions: OrderedDict[str, PracticeSession] = OrderedDict()
    worlds: OrderedDict[str, PracticeWorld] = OrderedDict()
    closes: dict[
        str, dict[str, int]
    ] = {}  # each account's last closing prices, so a new day opens where the last ended
    lock = threading.Lock()  # one request at a time touches the ledger and the sessions
    touched: dict[str, float] = {}  # when each live day was last used (monotonic seconds)
    saved: set[int] = set()  # practice worlds (by object id) whose day is already in the history

    # -- who is asking ---------------------------------------------------------------------------------------
    attempts = LedgerAttempts(ledger, lock)  # counted in the database, so several server processes share one count
    by_name = auth.RateLimit(30, 15 * 60, store=attempts, namespace="name")  # wrong secrets per username, anywhere
    by_pair = auth.RateLimit(5, 15 * 60, store=attempts, namespace="pair")  # per username from one address
    by_address = auth.RateLimit(100, 15 * 60, store=attempts, namespace="addr")  # from one address, any username
    new_accounts = auth.RateLimit(30, 60 * 60, store=attempts, namespace="new")  # new accounts and guests per address

    def identify(authorization: str | None) -> tuple[str, bool] | None:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        with lock:
            return ledger.login_user(auth.token_hash(token))

    def owner_of(authorization: str | None = Header(default=None)) -> str | None:
        """The signed-in name, or None when login is switched off. When it is on and nobody is signed in: 401."""
        if not require_login:
            return None
        found = identify(authorization)
        if found is None:
            raise HTTPException(401, "Sign in to play.")
        return found[0]

    def legacy_only() -> None:
        if require_login:
            raise HTTPException(404, "The older single-company sessions are switched off when login is on.")

    def issue(name: str) -> str:
        token = auth.new_token(name)
        with lock:
            ledger.purge_logins()
            ledger.add_login(auth.token_hash(token), name, days=TOKEN_DAYS)
        return token

    def save_day(pw: PracticeWorld) -> None:
        """Put the day in the history once: when it ends, or when it is abandoned after some trading."""
        if id(pw) in saved:
            return
        summary = pw.day_summary()
        if not pw.world.finished and not summary["fills"]:
            return  # a day walked away from before any trade is not worth keeping
        saved.add(id(pw))
        ledger.record_day(
            pw.owner, pw.config.seed, finished=pw.world.finished, closes=pw.world.prices(), summary=summary
        )

    def find_session(session_id: str) -> PracticeSession:
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(404, "unknown session: start one with POST /api/sessions (sessions are kept in memory)")
        return session

    def find_world(world_id: str, owner: str | None = None) -> PracticeWorld:
        world = worlds.get(world_id)
        if world is None or (owner is not None and world.owner != owner):  # someone else's day looks like no day
            raise HTTPException(404, "unknown world: start one with POST /api/worlds (worlds are kept in memory)")
        worlds.move_to_end(world_id)  # the order of `worlds` is "least recently used first"
        touched[world_id] = _now()
        return world

    def let_go(world_id: str) -> None:
        pw = worlds.pop(world_id)
        touched.pop(world_id, None)
        save_day(pw)
        pw.end_early()  # money set aside for waiting orders comes back

    def sweep() -> None:
        """Let go of days nobody has touched for IDLE_SECONDS, then of the least recently used if over the limit."""
        now = _now()
        for world_id in [i for i in worlds if now - touched.get(i, now) > IDLE_SECONDS]:
            let_go(world_id)
        while len(worlds) > MAX_WORLDS_KEPT:
            let_go(next(iter(worlds)))

    def new_events(pw: PracticeWorld, before: dict[str, int]) -> dict[str, Any]:
        sims = pw.world.sims
        return {
            "new_events": {s: [event_to_dict(e) for e in sim.events[before[s] :]] for s, sim in sims.items()},
            "new_ends": {s: [end for end in sim.ends if end > before[s]] for s, sim in sims.items()},
        }

    def counts(pw: PracticeWorld) -> dict[str, int]:
        return {s: len(sim.events) for s, sim in pw.world.sims.items()}

    def find(run_id: str) -> StoredRun:
        run = store.get(run_id)
        if run is None:
            raise HTTPException(404, "unknown run: start one with POST /api/runs (runs are kept in memory)")
        return run

    @app.get("/api/config")
    def config() -> dict[str, Any]:
        return {"login_required": require_login}

    def too_many(seconds: int) -> HTTPException:
        minutes = max(1, -(-seconds // 60))
        return HTTPException(
            429,
            f"Too many tries. Wait about {minutes} minute{'s' if minutes != 1 else ''} and try again.",
            headers={"Retry-After": str(seconds)},
        )

    @app.post("/api/auth/enter")
    def enter(body: EnterRequest, request: Request) -> dict[str, Any]:
        """One form for both: an existing username needs its secret; a free one is created (after a confirmation)."""
        username = body.username.strip()
        problem = auth.check_username(username)
        if problem:
            raise HTTPException(422, problem)
        who = username.lower()
        address = request.client.host if request.client else "unknown"
        pair = f"{who}|{address}"
        wait = max(by_name.wait(who), by_pair.wait(pair), by_address.wait(address))
        if wait:
            raise too_many(wait)
        with lock:
            found = ledger.user(username)
        if found is not None:
            name, stored, _guest = found
            if stored is None or not auth.verify_secret(body.secret, stored):  # guests have no secret: never enterable
                for limiter, key in ((by_name, who), (by_pair, pair), (by_address, address)):
                    limiter.hit(key)
                raise HTTPException(401, TAKEN_OR_WRONG)
            by_pair.clear(pair)
            return {"status": "signed_in", "username": name, "guest": False, "token": issue(name)}
        problem = auth.check_secret(body.secret, username)
        if problem:
            raise HTTPException(422, problem)
        if not body.create:
            return {"status": "confirm_new", "username": username}
        wait = new_accounts.wait(address)
        if wait:
            raise too_many(wait)
        hashed = auth.hash_secret(body.secret)  # slow on purpose, and done before taking the lock
        with lock:
            created = ledger.create_user(username, hashed)
        if not created:  # someone took the name a moment ago
            raise HTTPException(401, TAKEN_OR_WRONG)
        new_accounts.hit(address)
        return {"status": "created", "username": username, "guest": False, "token": issue(username)}

    @app.post("/api/auth/guest")
    def guest(request: Request) -> dict[str, Any]:
        """A throwaway account with no secret, for a quick look. Its token is its only key."""
        address = request.client.host if request.client else "unknown"
        wait = new_accounts.wait(address)
        if wait:
            raise too_many(wait)
        while True:
            name = auth.new_guest_name()
            with lock:
                if ledger.create_user(name, None, guest=True):
                    break
        new_accounts.hit(address)
        return {"status": "created", "username": name, "guest": True, "token": issue(name)}

    @app.get("/api/auth/me")
    def me(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        found = identify(authorization)
        if found is None:
            raise HTTPException(401, "Sign in to play.")
        return {"username": found[0], "guest": found[1]}

    @app.post("/api/auth/logout")
    def logout(authorization: str | None = Header(default=None)) -> dict[str, bool]:
        _, _, token = (authorization or "").partition(" ")
        if token:
            with lock:
                ledger.end_login(auth.token_hash(token))
        return {"ok": True}

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/runs")
    def start_run(request: RunRequest | None = None) -> dict[str, Any]:
        request = request or RunRequest.model_validate({})
        company = BY_SYMBOL.get(request.company) if request.company else None
        if request.company and company is None:
            raise HTTPException(422, f"there is no company with the symbol {request.company}")
        config = SimConfig(
            seed=request.seed,
            symbol=company.symbol if company else "DEMO1",
            reference_price=company.price if company else 250_000,
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

    @app.post("/api/sessions", dependencies=[Depends(legacy_only)])
    def start_session(request: SessionRequest | None = None) -> dict[str, Any]:
        request = request or SessionRequest.model_validate({})
        config = SimConfig(
            seed=request.seed,
            open_seconds=request.open_seconds,
            pre_open_seconds=request.pre_open_seconds,
            noise_traders=request.noise_traders,
        )
        with lock:
            for old_id in [i for i, other in sessions.items() if other.owner == request.owner]:
                sessions.pop(old_id).end_early()  # one day at a time per account; money set aside comes back
            try:
                session = PracticeSession(
                    config, ledger, request.owner, plan=request.plan, trading_date=request.trading_date
                )
            except ValueError as error:  # for example a date before the first recorded charge schedule
                raise HTTPException(422, str(error)) from error
            session_id = secrets.token_hex(6)
            sessions[session_id] = session
            while len(sessions) > MAX_SESSIONS_KEPT:
                sessions.popitem(last=False)[1].end_early()
            return {
                **session_json(session_id, session),
                "plan": PLANS[request.plan].description,
                "new_events": [event_to_dict(e) for e in session.sim.events],
                "new_ends": ends_after(session, 0),
            }

    @app.get("/api/sessions/{session_id}", dependencies=[Depends(legacy_only)])
    def get_session(session_id: str) -> dict[str, Any]:
        with lock:
            return session_json(session_id, find_session(session_id))

    @app.get("/api/sessions/{session_id}/market", dependencies=[Depends(legacy_only)])
    def session_market(session_id: str, levels: int = Query(10, ge=1, le=100)) -> dict[str, Any]:
        with lock:
            return state_json(find_session(session_id).sim.state, levels)

    @app.get("/api/sessions/{session_id}/statement", dependencies=[Depends(legacy_only)])
    def session_statement(session_id: str) -> dict[str, Any]:
        with lock:
            return statement_json(find_session(session_id))

    @app.post("/api/sessions/{session_id}/advance", dependencies=[Depends(legacy_only)])
    def advance_session(session_id: str, request: AdvanceRequest) -> dict[str, Any]:
        with lock:
            session = find_session(session_id)
            before = len(session.sim.events)
            result = session.advance(request.seconds, pause_on_fill=request.pause_on_fill)
            return {
                "new_events": [event_to_dict(e) for e in result.events],
                "new_ends": ends_after(session, before),
                "now": result.now,
                "stopped_for_fill": result.stopped_for_fill,
                "finished": result.finished,
                "events": len(session.sim.events),
                "portfolio": portfolio_json(session.portfolio()),
            }

    @app.post("/api/sessions/{session_id}/orders", dependencies=[Depends(legacy_only)])
    def place_order(session_id: str, request: OrderRequest) -> dict[str, Any]:
        with lock:
            session = find_session(session_id)
            before = len(session.sim.events)
            try:
                order_id, events = session.place(
                    Side(request.side), request.quantity, request.limit_price, TimeInForce(request.tif)
                )
            except OrderRefused as refused:
                raise HTTPException(422, str(refused)) from refused
            return {
                "order_id": order_id,
                "new_events": [event_to_dict(e) for e in events],
                "new_ends": ends_after(session, before),
                "now": session.now,
                "portfolio": portfolio_json(session.portfolio()),
            }

    @app.delete("/api/sessions/{session_id}/orders/{order_id}", dependencies=[Depends(legacy_only)])
    def cancel_order(session_id: str, order_id: int) -> dict[str, Any]:
        with lock:
            session = find_session(session_id)
            before = len(session.sim.events)
            try:
                events = session.cancel(order_id)
            except OrderRefused as refused:
                raise HTTPException(422, str(refused)) from refused
            return {
                "new_events": [event_to_dict(e) for e in events],
                "new_ends": ends_after(session, before),
                "now": session.now,
                "portfolio": portfolio_json(session.portfolio()),
            }

    @app.delete("/api/sessions/{session_id}", dependencies=[Depends(legacy_only)])
    def end_session(session_id: str) -> dict[str, Any]:
        with lock:
            session = find_session(session_id)
            session.end_early()
            sessions.pop(session_id, None)
            return {"ended": True, "portfolio": portfolio_json(session.portfolio())}

    @app.post("/api/worlds")
    def start_world(request: WorldRequest | None = None, who: str | None = Depends(owner_of)) -> dict[str, Any]:
        request = request or WorldRequest.model_validate({})
        name = who or request.owner  # signed in: always your own account, whatever the request says
        config = WorldConfig(
            seed=request.seed, open_seconds=request.open_seconds, pre_open_seconds=request.pre_open_seconds
        )
        with lock:
            for old_id in [i for i, other in worlds.items() if other.owner == name]:
                let_go(old_id)  # one day at a time per account
            try:
                pw = PracticeWorld(
                    config,
                    ledger,
                    name,
                    plan=request.plan,
                    trading_date=request.trading_date,
                    previous_close=None if request.fresh_prices else closes.get(name) or ledger.last_closes(name),
                )
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            world_id = secrets.token_hex(6)
            worlds[world_id] = pw
            touched[world_id] = _now()
            sweep()
            return {
                **world_json(world_id, pw),
                "plan": PLANS[request.plan].description,
                **new_events(pw, dict.fromkeys(pw.world.sims, 0)),
            }

    @app.get("/api/accounts/{owner}/days")
    def account_days(owner: str, who: str | None = Depends(owner_of)) -> dict[str, Any]:
        """Every practice day this account has played, newest first, with each trade. Kept in the database file."""
        if who is not None and who.lower() != owner.lower():
            raise HTTPException(403, "You can only see your own days.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", owner):
            raise HTTPException(422, "an account name is letters, numbers, - and _ only")
        with lock:
            return {"owner": owner, "days": ledger.days(owner)}

    @app.get("/api/worlds/{world_id}")
    def get_world(world_id: str, owner: str | None = Depends(owner_of)) -> dict[str, Any]:
        with lock:
            return world_json(world_id, find_world(world_id, owner))

    @app.get("/api/worlds/{world_id}/statement")
    def world_statement(world_id: str, owner: str | None = Depends(owner_of)) -> dict[str, Any]:
        with lock:
            pw = find_world(world_id, owner)
            statement = pw.statement()
            prices = pw.world.prices()
            listed = [(s, q) for s, q in statement.holdings if s in prices]
            return {
                "rows": [
                    {
                        "at": r.at,
                        "kind": r.kind,
                        "memo": r.memo,
                        "symbol": r.symbol,
                        "shares_change": r.shares_change,
                        "value": r.value,
                        "charges": {line: amount for line, amount in r.charges},
                        "money_change": r.money_change,
                        "money_after": r.money_after,
                    }
                    for r in statement.rows
                ],
                "starting_money": statement.starting_money,
                "money": statement.money,
                "holdings": dict(listed),
                "bought": statement.bought,
                "sold": statement.sold,
                "traded_value": statement.traded_value,
                "charges_by_line": statement.charges_by_line,
                "total_charges": statement.total_charges,
                "charges_basis_points": statement.charges_basis_points,
                "worth": statement.money + sum(q * prices[s] for s, q in listed),
                "problems": statement.check() + pw.ledger.verify(),
            }

    @app.post("/api/worlds/{world_id}/advance")
    def advance_world(world_id: str, request: AdvanceRequest, owner: str | None = Depends(owner_of)) -> dict[str, Any]:
        with lock:
            pw = find_world(world_id, owner)
            before = counts(pw)
            result = pw.advance(request.seconds, pause_on_fill=request.pause_on_fill)
            if result.finished:
                closes[pw.owner] = pw.world.prices()
                save_day(pw)
            return {
                **new_events(pw, before),
                "now": result.now,
                "stopped_for_fill": result.stopped_for_fill,
                "finished": result.finished,
                "snapshot": world_json(world_id, pw),
            }

    @app.post("/api/worlds/{world_id}/orders")
    def place_world_order(
        world_id: str, request: WorldOrderRequest, owner: str | None = Depends(owner_of)
    ) -> dict[str, Any]:
        with lock:
            pw = find_world(world_id, owner)
            before = counts(pw)
            try:
                order_id, _ = pw.place(
                    request.symbol, Side(request.side), request.quantity, request.limit_price, TimeInForce(request.tif)
                )
            except OrderRefused as refused:
                raise HTTPException(422, str(refused)) from refused
            return {"order_id": order_id, **new_events(pw, before), "now": pw.now, "snapshot": world_json(world_id, pw)}

    @app.delete("/api/worlds/{world_id}/orders/{symbol}/{order_id}")
    def cancel_world_order(
        world_id: str, symbol: str, order_id: int, owner: str | None = Depends(owner_of)
    ) -> dict[str, Any]:
        with lock:
            pw = find_world(world_id, owner)
            before = counts(pw)
            try:
                pw.cancel(symbol, order_id)
            except OrderRefused as refused:
                raise HTTPException(422, str(refused)) from refused
            return {**new_events(pw, before), "now": pw.now, "snapshot": world_json(world_id, pw)}

    @app.delete("/api/worlds/{world_id}")
    def end_world(world_id: str, owner: str | None = Depends(owner_of)) -> dict[str, Any]:
        with lock:
            pw = find_world(world_id, owner)
            save_day(pw)
            pw.end_early()
            worlds.pop(world_id, None)
            touched.pop(world_id, None)
            return {"ended": True, "snapshot": world_json(world_id, pw)}

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
