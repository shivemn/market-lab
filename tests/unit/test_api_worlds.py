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
