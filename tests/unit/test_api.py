"""The web API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from marketlab.api import create_app
from marketlab.codec import event_to_dict
from marketlab.core import Side
from marketlab.projection import MarketState
from marketlab.sim import SimConfig, run_simulation

SMALL: dict[str, Any] = {"seed": 4, "open_seconds": 20, "pre_open_seconds": 5, "noise_traders": 4}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def run(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/runs", json=SMALL)
    assert response.status_code == 200
    return dict(response.json())


def expected_result() -> Any:
    return run_simulation(SimConfig(**SMALL))


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_starting_a_run_returns_its_summary(run: dict[str, Any]) -> None:
    result = expected_result()
    assert run["id"] == result.sha256[:12]
    assert run["sha256"] == result.sha256
    assert run["events"] == len(result.events)
    assert run["commands"] == len(result.ends)
    assert run["config"]["seed"] == 4
    assert run["instrument"]["symbol"] == "DEMO1" and run["instrument"]["band_low"] == 225_000


def test_the_same_settings_give_the_same_run_id(client: TestClient, run: dict[str, Any]) -> None:
    assert client.post("/api/runs", json=SMALL).json()["id"] == run["id"]
    assert client.get(f"/api/runs/{run['id']}").json() == run


def test_a_run_with_no_body_uses_the_defaults(client: TestClient) -> None:
    response = client.post("/api/runs")
    assert response.status_code == 200 and response.json()["config"]["seed"] == 1


@pytest.mark.parametrize(
    "body",
    [{"open_seconds": 5}, {"open_seconds": 99_999}, {"noise_traders": 500}, {"seed": -1}, {"seed": "x"}],
)
def test_silly_settings_are_refused(client: TestClient, body: dict[str, Any]) -> None:
    assert client.post("/api/runs", json=body).status_code == 422


def test_unknown_run_is_a_404(client: TestClient) -> None:
    for path in ("", "/events", "/ends", "/state?at=0"):
        assert client.get(f"/api/runs/nope{path}").status_code == 404


def test_events_are_paged_and_match_the_simulation(client: TestClient, run: dict[str, Any]) -> None:
    result = expected_result()
    everything: list[dict[str, Any]] = []
    start = 0
    while True:
        page = client.get(f"/api/runs/{run['id']}/events", params={"start": start, "limit": 100}).json()
        assert page["total"] == len(result.events) and page["start"] == start
        everything += page["events"]
        start += 100
        if start >= page["total"]:
            break
    assert everything == [event_to_dict(e) for e in result.events]
    assert client.get(f"/api/runs/{run['id']}/events", params={"limit": 0}).status_code == 422


def test_ends(client: TestClient, run: dict[str, Any]) -> None:
    assert client.get(f"/api/runs/{run['id']}/ends").json() == {"ends": expected_result().ends}


def test_state_matches_the_fold_and_snaps_back_to_a_finished_command(client: TestClient, run: dict[str, Any]) -> None:
    result = expected_result()
    middle = result.ends[len(result.ends) // 2]
    snap = client.get(f"/api/runs/{run['id']}/state", params={"at": middle}).json()
    assert snap["at"] == middle
    state = MarketState(result.instrument)
    state.apply_all(result.events[:middle])
    assert snap["last_price"] == state.last_price and snap["volume"] == state.volume
    assert [(level["price"], level["quantity"]) for level in snap["bids"]] == [
        (v.price, v.quantity) for v in state.depth(Side.BUY, 10)
    ]
    assert snap["session"] == "OPEN"
    # Asking for a position in the middle of a command gives the last finished one.
    inside = next(n for n in range(1, len(result.events)) if n not in set(result.ends))
    assert client.get(f"/api/runs/{run['id']}/state", params={"at": inside}).json()["at"] < inside
    assert client.get(f"/api/runs/{run['id']}/state", params={"at": 0}).json()["at"] == 0
    beyond = client.get(f"/api/runs/{run['id']}/state", params={"at": 10**9}).json()
    assert beyond["at"] == len(result.events) and beyond["session"] == "CLOSED"


def collect(ws: Any) -> list[dict[str, Any]]:
    messages = []
    while True:
        message = ws.receive_json()
        messages.append(message)
        if message["type"] == "done":
            return messages


def test_the_stream_delivers_every_event_one_command_at_a_time(client: TestClient, run: dict[str, Any]) -> None:
    result = expected_result()
    with client.websocket_connect(f"/ws/runs/{run['id']}?speed=1000000") as ws:
        messages = collect(ws)
    assert messages[0]["type"] == "hello" and messages[0]["run"]["id"] == run["id"]
    batches = [m for m in messages if m["type"] == "batch"]
    assert [b["upto"] for b in batches] == result.ends
    assert [e for b in batches for e in b["events"]] == [event_to_dict(e) for e in result.events]
    assert messages[-1] == {"type": "done"}


def test_stream_accepts_control_messages(client: TestClient, run: dict[str, Any]) -> None:
    with client.websocket_connect(f"/ws/runs/{run['id']}?speed=1000000") as ws:
        ws.send_json({"type": "pause"})
        ws.send_json({"type": "speed", "value": 5_000_000})
        ws.send_json({"type": "speed", "value": "fast"})  # ignored
        ws.send_json({"type": "resume"})
        messages = collect(ws)
    assert messages[-1]["type"] == "done"


def test_a_reconnecting_viewer_can_ask_to_skip_ahead(client: TestClient, run: dict[str, Any]) -> None:
    result = expected_result()
    with client.websocket_connect(f"/ws/runs/{run['id']}?speed=1000000&start={result.ends[10]}") as ws:
        messages = collect(ws)
    assert [m["upto"] for m in messages if m["type"] == "batch"] == result.ends  # same batches, just no waiting


def test_unknown_run_closes_the_stream(client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as info, client.websocket_connect("/ws/runs/nope") as ws:
        ws.receive_json()
    assert info.value.code == 4404


def test_the_built_dashboard_is_served_when_present(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<h1>dashboard</h1>", encoding="utf-8")
    client = TestClient(create_app(tmp_path))
    assert "dashboard" in client.get("/").text
    assert client.get("/api/health").status_code == 200  # the API still works beside it


def test_only_a_few_runs_are_kept(client: TestClient) -> None:
    ids = [
        client.post("/api/runs", json={**SMALL, "seed": seed, "open_seconds": 10}).json()["id"] for seed in range(20)
    ]
    assert client.get(f"/api/runs/{ids[-1]}").status_code == 200
    assert client.get(f"/api/runs/{ids[0]}").status_code == 404


def test_the_same_settings_are_simulated_once() -> None:
    from unittest import mock

    import marketlab.api.app as app_module

    client = TestClient(create_app())
    with mock.patch.object(app_module, "run_simulation", side_effect=run_simulation) as spy:
        first = client.post("/api/runs", json={"open_seconds": 20, "pre_open_seconds": 5}).json()
        second = client.post("/api/runs", json={"open_seconds": 20, "pre_open_seconds": 5}).json()
        third = client.post("/api/runs", json={"open_seconds": 21, "pre_open_seconds": 5}).json()
    assert first == second and first["id"] != third["id"]
    assert spy.call_count == 2
