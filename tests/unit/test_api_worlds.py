"""The twelve-company part of the web API."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from marketlab.api import create_app
from marketlab.ledger import STARTING_CASH

SMALL: dict[str, Any] = {"seed": 5, "open_seconds": 30, "pre_open_seconds": 5, "trading_date": "2026-11-01"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def start(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/worlds", json=SMALL)
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_starting_a_world_lists_twelve_companies_in_four_sectors(client: TestClient) -> None:
    world = start(client)
    assert len(world["companies"]) == 12 and len(world["sectors"]) == 4
    assert world["portfolio"]["cash"] == STARTING_CASH
    assert set(world["new_events"]) == {c["symbol"] for c in world["companies"]}
    assert all(world["new_events"][s] for s in world["new_events"])  # each has its opening session event
    assert world["indices"]["cap"]["level"] == 100_000  # 1000.00 at the start, in hundredths
    assert world["worth"] == STARTING_CASH


def test_advancing_returns_new_events_per_company_and_a_fresh_snapshot(client: TestClient) -> None:
    world = start(client)
    wid = world["id"]
    first = client.post(f"/api/worlds/{wid}/advance", json={"seconds": 10, "pause_on_fill": False}).json()
    assert first["now"] == 10_000_000
    assert sum(len(v) for v in first["new_events"].values()) > 0
    again = client.post(f"/api/worlds/{wid}/advance", json={"seconds": 5, "pause_on_fill": False}).json()
    last_before = max(e["seq"] for e in first["new_events"]["UDHAAR"])
    assert all(e["seq"] > last_before for e in again["new_events"]["UDHAAR"])  # only what is new, in order
    assert set(again["snapshot"]["indices"]) == {"cap", "equal", "price", "sectors"}


def test_an_order_is_placed_in_one_company_and_shows_in_the_portfolio(client: TestClient) -> None:
    wid = start(client)["id"]
    client.post(f"/api/worlds/{wid}/advance", json={"seconds": 8, "pause_on_fill": False})
    placed = client.post(f"/api/worlds/{wid}/orders", json={"symbol": "KIRANA", "side": "BUY", "quantity": 2})
    assert placed.status_code == 200, placed.text
    body = placed.json()
    assert body["snapshot"]["portfolio"]["holdings"]["KIRANA"]["shares"] in (0, 1, 2)
    client.post(f"/api/worlds/{wid}/advance", json={"seconds": 20})
    snap = client.get(f"/api/worlds/{wid}").json()
    assert snap["positions"]["KIRANA"]["shares"] == 2
    statement = client.get(f"/api/worlds/{wid}/statement").json()
    assert statement["problems"] == []
    assert any(r["symbol"] == "KIRANA" and r["kind"] == "buy" for r in statement["rows"])


def test_refusals_are_422_with_a_reason(client: TestClient) -> None:
    wid = start(client)["id"]
    response = client.post(f"/api/worlds/{wid}/orders", json={"symbol": "NOSUCH", "side": "BUY", "quantity": 1})
    assert response.status_code == 422 and "no company" in response.json()["detail"]
    too_big = client.post(f"/api/worlds/{wid}/orders", json={"symbol": "BUGFIX", "side": "BUY", "quantity": 500})
    assert too_big.status_code == 422 and "available" in too_big.json()["detail"]
    assert client.get("/api/worlds/nope").status_code == 404


def test_cancel_and_leave_return_the_money(client: TestClient) -> None:
    wid = start(client)["id"]
    client.post(f"/api/worlds/{wid}/advance", json={"seconds": 8, "pause_on_fill": False})
    price = client.get(f"/api/worlds/{wid}").json()["prices"]["PAKKA"]
    order = client.post(
        f"/api/worlds/{wid}/orders",
        json={"symbol": "PAKKA", "side": "BUY", "quantity": 3, "limit_price": price - 300},
    ).json()
    assert order["snapshot"]["portfolio"]["reserved"] > 0
    cancelled = client.delete(f"/api/worlds/{wid}/orders/PAKKA/{order['order_id']}")
    assert cancelled.status_code == 200 and cancelled.json()["snapshot"]["portfolio"]["reserved"] == 0
    left = client.delete(f"/api/worlds/{wid}").json()
    assert left["ended"] is True
    assert client.get(f"/api/worlds/{wid}").status_code == 404


def test_the_next_day_opens_at_the_last_close_unless_fresh_prices_are_asked_for(client: TestClient) -> None:
    first = start(client)
    wid = first["id"]
    done = client.post(f"/api/worlds/{wid}/advance", json={"seconds": 100, "pause_on_fill": False}).json()
    assert done["finished"] is True
    closes = done["snapshot"]["prices"]
    second = client.post("/api/worlds", json={**SMALL, "seed": 6}).json()
    assert {c["symbol"]: c["instrument"]["reference_price"] for c in second["companies"]} == closes
    fresh = client.post("/api/worlds", json={**SMALL, "seed": 7, "fresh_prices": True}).json()
    assert fresh["indices"]["cap"]["level"] == 100_000


def test_the_single_stock_day_can_use_a_company_from_the_catalogue(client: TestClient) -> None:
    run = client.post("/api/runs", json={"seed": 1, "open_seconds": 10, "pre_open_seconds": 5, "company": "UDHAAR"})
    assert run.status_code == 200
    assert run.json()["instrument"]["symbol"] == "UDHAAR" and run.json()["instrument"]["reference_price"] == 164_220
    assert client.post("/api/runs", json={"company": "NOSUCH"}).status_code == 422


def play_to_the_close(client: TestClient, wid: str, symbol: str = "UDHAAR") -> None:
    client.post(f"/api/worlds/{wid}/advance", json={"seconds": 6, "pause_on_fill": False})
    client.post(f"/api/worlds/{wid}/orders", json={"symbol": symbol, "side": "BUY", "quantity": 3, "limit_price": None})
    for _ in range(20):
        reply = client.post(f"/api/worlds/{wid}/advance", json={"seconds": 10, "pause_on_fill": False}).json()
        if reply["finished"]:
            return
    raise AssertionError("the day never finished")


def test_a_finished_day_is_kept_in_the_history_with_its_trades(client: TestClient) -> None:
    wid = start(client)["id"]
    assert client.get("/api/accounts/you/days").json()["days"] == []
    play_to_the_close(client, wid)
    days = client.get("/api/accounts/you/days").json()["days"]
    assert len(days) == 1
    day = days[0]
    assert day["seed"] == 5 and day["finished"] is True
    buys = [f for f in day["fills"] if f["side"] == "BUY"]
    assert buys and all(f["symbol"] == "UDHAAR" for f in buys)
    assert sum(f["quantity"] for f in buys) == 3
    assert day["end_worth"] - day["start_worth"] == day["result"]
    # asking again for the end of the same day does not write it twice
    client.post(f"/api/worlds/{wid}/advance", json={"seconds": 1, "pause_on_fill": False})
    assert len(client.get("/api/accounts/you/days").json()["days"]) == 1


def test_a_day_walked_away_from_is_kept_only_if_something_traded(client: TestClient) -> None:
    wid = start(client)["id"]
    client.delete(f"/api/worlds/{wid}")
    assert client.get("/api/accounts/you/days").json()["days"] == []
    wid = start(client)["id"]
    client.post(f"/api/worlds/{wid}/advance", json={"seconds": 6, "pause_on_fill": False})
    client.post(
        f"/api/worlds/{wid}/orders", json={"symbol": "BIJLI", "side": "BUY", "quantity": 2, "limit_price": None}
    )
    client.post(f"/api/worlds/{wid}/advance", json={"seconds": 3, "pause_on_fill": False})
    client.delete(f"/api/worlds/{wid}")
    days = client.get("/api/accounts/you/days").json()["days"]
    assert len(days) == 1 and days[0]["finished"] is False


def test_history_and_closing_prices_survive_a_restart(tmp_path: Any) -> None:
    path = str(tmp_path / "practice.db")
    first = TestClient(create_app(db_path=path))
    wid = first.post("/api/worlds", json=SMALL).json()["id"]
    play_to_the_close(first, wid)
    closes = first.get(f"/api/worlds/{wid}").json()["prices"]
    second = TestClient(create_app(db_path=path))  # a new server process on the same file
    assert len(second.get("/api/accounts/you/days").json()["days"]) == 1
    reopened = second.post("/api/worlds", json={**SMALL, "seed": 6}).json()
    assert reopened["indices"]["cap"]["open"] == first.get(f"/api/worlds/{wid}").json()["indices"]["cap"]["level"]
    assert closes  # the new day opened from the saved closes, not the starting prices


def test_history_rejects_a_bad_account_name(client: TestClient) -> None:
    assert client.get("/api/accounts/a%20b/days").status_code == 422
