"""The practice-session part of the web API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from marketlab.api import create_app
from marketlab.ledger import STARTING_CASH

SMALL: dict[str, Any] = {
    "seed": 5,
    "open_seconds": 30,
    "pre_open_seconds": 5,
    "noise_traders": 6,
    "trading_date": "2026-11-01",
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def start(client: TestClient, **extra: Any) -> dict[str, Any]:
    response = client.post("/api/sessions", json={**SMALL, **extra})
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_starting_a_session_returns_the_opening_events_and_a_funded_account(client: TestClient) -> None:
    session = start(client)
    assert session["now"] == 0 and session["finished"] is False
    assert session["portfolio"] == {
        "cash": STARTING_CASH,
        "reserved": 0,
        "shares": 0,
        "locked": 0,
        "open_orders": [],
    }
    assert session["new_events"][0]["type"] == "SessionChanged"
    assert session["instrument"]["band_high"] == 275_000
    assert "brokerage" in session["plan"]


def test_the_day_moves_only_when_asked(client: TestClient) -> None:
    session = start(client)
    sid = session["id"]
    assert client.get(f"/api/sessions/{sid}").json()["now"] == 0
    moved = client.post(f"/api/sessions/{sid}/advance", json={"seconds": 12.5}).json()
    assert moved["now"] == 12_500_000 and moved["finished"] is False
    assert moved["new_events"], "a few traders should have acted by then"
    assert client.get(f"/api/sessions/{sid}").json()["now"] == 12_500_000


def test_placing_and_cancelling_an_order_moves_money_in_and_out_of_set_aside(client: TestClient) -> None:
    sid = start(client)["id"]
    client.post(f"/api/sessions/{sid}/advance", json={"seconds": 10})
    placed = client.post(
        f"/api/sessions/{sid}/orders", json={"side": "BUY", "quantity": 10, "limit_price": 225_000}
    ).json()
    folio = placed["portfolio"]
    assert folio["reserved"] > 10 * 225_000 and folio["cash"] == STARTING_CASH - folio["reserved"]
    assert [o["id"] for o in folio["open_orders"]] == [placed["order_id"]]
    cancelled = client.delete(f"/api/sessions/{sid}/orders/{placed['order_id']}").json()
    assert cancelled["portfolio"]["reserved"] == 0 and cancelled["portfolio"]["cash"] == STARTING_CASH


def test_a_refusal_is_a_422_with_the_reason_in_plain_words_and_changes_nothing(client: TestClient) -> None:
    sid = start(client)["id"]
    client.post(f"/api/sessions/{sid}/advance", json={"seconds": 10})
    refused = client.post(
        f"/api/sessions/{sid}/orders", json={"side": "BUY", "quantity": 100_000, "limit_price": 275_000}
    )
    assert refused.status_code == 422
    assert "available" in refused.json()["detail"] and "could cost up to" in refused.json()["detail"]
    sold = client.post(f"/api/sessions/{sid}/orders", json={"side": "SELL", "quantity": 1})
    assert sold.status_code == 422 and "free to sell" in sold.json()["detail"]
    assert client.get(f"/api/sessions/{sid}").json()["portfolio"]["cash"] == STARTING_CASH


def test_bad_input_is_rejected_before_it_gets_near_the_ledger(client: TestClient) -> None:
    sid = start(client)["id"]
    for body in (
        {"side": "HOLD", "quantity": 1},
        {"side": "BUY", "quantity": 0},
        {"side": "BUY", "quantity": 1, "limit_price": 0},
        {"side": "BUY", "quantity": 1, "tif": "FOREVER"},
    ):
        assert client.post(f"/api/sessions/{sid}/orders", json=body).status_code == 422


def test_cancelling_an_order_that_is_not_open_is_a_422(client: TestClient) -> None:
    sid = start(client)["id"]
    assert client.delete(f"/api/sessions/{sid}/orders/12345").status_code == 422


def test_unknown_sessions_are_404(client: TestClient) -> None:
    assert client.get("/api/sessions/nope").status_code == 404
    assert client.post("/api/sessions/nope/advance", json={"seconds": 1}).status_code == 404


def test_a_whole_day_can_be_played_and_ends_with_nothing_set_aside(client: TestClient) -> None:
    sid = start(client)["id"]
    client.post(f"/api/sessions/{sid}/advance", json={"seconds": 10})
    client.post(f"/api/sessions/{sid}/orders", json={"side": "BUY", "quantity": 4})  # a market buy
    client.post(f"/api/sessions/{sid}/orders", json={"side": "BUY", "quantity": 5, "limit_price": 225_000})
    last: dict[str, Any] = {}
    for _ in range(200):
        last = client.post(f"/api/sessions/{sid}/advance", json={"seconds": 5, "pause_on_fill": False}).json()
        if last["finished"]:
            break
    assert last["finished"]
    assert last["portfolio"]["reserved"] == 0 and last["portfolio"]["open_orders"] == []
    assert last["portfolio"]["shares"] == 4
    assert client.post(f"/api/sessions/{sid}/orders", json={"side": "BUY", "quantity": 1}).status_code == 422


def test_starting_a_new_day_for_the_same_account_returns_money_set_aside_by_the_old_one(client: TestClient) -> None:
    first = start(client)["id"]
    client.post(f"/api/sessions/{first}/advance", json={"seconds": 10})
    client.post(f"/api/sessions/{first}/orders", json={"side": "BUY", "quantity": 10, "limit_price": 225_000})
    second = start(client, seed=6)
    assert second["portfolio"]["cash"] == STARTING_CASH and second["portfolio"]["reserved"] == 0
    assert client.get(f"/api/sessions/{first}").status_code == 404  # one day at a time per account


def test_ending_a_session_early_returns_what_is_set_aside(client: TestClient) -> None:
    sid = start(client)["id"]
    client.post(f"/api/sessions/{sid}/advance", json={"seconds": 10})
    client.post(f"/api/sessions/{sid}/orders", json={"side": "BUY", "quantity": 10, "limit_price": 225_000})
    ended = client.delete(f"/api/sessions/{sid}").json()
    assert ended["portfolio"]["cash"] == STARTING_CASH
    assert client.get(f"/api/sessions/{sid}").status_code == 404


def test_cash_and_shares_carry_over_to_the_next_day_through_the_database_file(tmp_path: Path) -> None:
    db = str(tmp_path / "practice.db")
    one = TestClient(create_app(db_path=db))
    sid = start(one)["id"]
    one.post(f"/api/sessions/{sid}/advance", json={"seconds": 10})
    one.post(f"/api/sessions/{sid}/orders", json={"side": "BUY", "quantity": 3})
    one.post(f"/api/sessions/{sid}/advance", json={"seconds": 100, "pause_on_fill": False})
    after = one.get(f"/api/sessions/{sid}").json()["portfolio"]
    assert after["shares"] == 3 and after["cash"] < STARTING_CASH

    # the server is restarted: a new app on the same file still knows the account
    two = TestClient(create_app(db_path=db))
    again = start(two, seed=9)["portfolio"]
    assert (again["cash"], again["shares"]) == (after["cash"], 3)


def test_the_market_view_shows_the_book_as_it_stands(client: TestClient) -> None:
    sid = start(client)["id"]
    client.post(f"/api/sessions/{sid}/advance", json={"seconds": 20})
    market = client.get(f"/api/sessions/{sid}/market").json()
    assert market["session"] == "OPEN" and market["bids"] and market["asks"]


def test_every_reply_says_where_commands_end_so_a_client_can_fold_whole_commands(client: TestClient) -> None:
    opened = start(client)
    sid = opened["id"]
    have = len(opened["new_events"])
    assert opened["new_ends"] and opened["new_ends"][-1] == have
    everything = list(opened["new_ends"])
    replies = [
        client.post(f"/api/sessions/{sid}/advance", json={"seconds": 20}).json(),
        client.post(f"/api/sessions/{sid}/orders", json={"side": "BUY", "quantity": 1, "limit_price": 225_000}).json(),
    ]
    for reply in replies:
        before = have
        have += len(reply["new_events"])
        assert all(end > before for end in reply["new_ends"])
        if reply["new_events"]:
            assert reply["new_ends"][-1] == have  # the last new event always finishes a command
        everything += reply["new_ends"]
    assert everything == sorted(set(everything)), "boundaries only ever grow, never repeat"
