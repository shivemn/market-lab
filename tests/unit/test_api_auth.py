"""Signing in: one form for new and returning people, guests, and keeping other people's days out of reach."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from marketlab.api import create_app

SMALL: dict[str, Any] = {"seed": 5, "open_seconds": 30, "pre_open_seconds": 5, "trading_date": "2026-11-01"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(require_login=True))


def enter(client: TestClient, username: str, secret: str, create: bool = False) -> Any:
    return client.post("/api/auth/enter", json={"username": username, "secret": secret, "create": create})


def sign_up(client: TestClient, username: str, secret: str = "purple4217") -> dict[str, str]:
    reply = enter(client, username, secret, create=True)
    assert reply.status_code == 200, reply.text
    return {"Authorization": f"Bearer {reply.json()['token']}"}


def test_login_is_off_by_default_so_the_old_behaviour_is_unchanged() -> None:
    plain = TestClient(create_app())
    assert plain.get("/api/config").json() == {"login_required": False}
    assert plain.post("/api/worlds", json={**SMALL, "owner": "anyone"}).status_code == 200


def test_the_page_can_ask_whether_login_is_needed(client: TestClient) -> None:
    assert client.get("/api/config").json() == {"login_required": True}


def test_a_new_name_asks_for_confirmation_before_an_account_is_made(client: TestClient) -> None:
    first = enter(client, "shivam", "purple4217").json()
    assert first == {"status": "confirm_new", "username": "shivam"}  # nothing created yet: a typo costs nothing
    assert enter(client, "shivam", "purple4217").json()["status"] == "confirm_new"
    made = enter(client, "shivam", "purple4217", create=True).json()
    assert made["status"] == "created" and made["token"] and made["guest"] is False


def test_the_same_form_signs_a_returning_person_in(client: TestClient) -> None:
    sign_up(client, "Shivam")
    again = enter(client, "shivam", "  PURPLE4217")  # capitals in the name and secret do not matter
    assert again.status_code == 200
    assert again.json()["status"] == "signed_in" and again.json()["username"] == "Shivam"


def test_a_taken_name_with_the_wrong_secret_is_refused_without_saying_which(client: TestClient) -> None:
    sign_up(client, "shivam")
    wrong = enter(client, "shivam", "tiger7777", create=True)  # even asking to create it does not get in
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "That username is taken, or the secret is wrong."


def test_bad_names_and_weak_secrets_are_explained(client: TestClient) -> None:
    assert enter(client, "a b", "purple4217").status_code == 422
    weak = enter(client, "newname", "12345678")
    assert weak.status_code == 422 and "word" in weak.json()["detail"]
    assert enter(client, "newname", "abc").status_code == 422


def test_five_wrong_tries_lock_the_name_for_a_while_even_for_the_right_secret(client: TestClient) -> None:
    sign_up(client, "shivam")
    for _ in range(5):
        assert enter(client, "shivam", "wrongwrong1").status_code == 401
    locked = enter(client, "shivam", "purple4217")
    assert locked.status_code == 429 and int(locked.headers["Retry-After"]) > 0
    assert "minute" in locked.json()["detail"]


def test_a_right_secret_clears_the_count(client: TestClient) -> None:
    sign_up(client, "shivam")
    for _ in range(4):
        enter(client, "shivam", "wrongwrong1")
    assert enter(client, "shivam", "purple4217").status_code == 200
    for _ in range(4):
        assert enter(client, "shivam", "wrongwrong1").status_code == 401  # a fresh allowance of five


def test_a_guest_gets_a_throwaway_name_and_can_play(client: TestClient) -> None:
    guest = client.post("/api/auth/guest").json()
    assert guest["guest"] is True and guest["username"].startswith("guest-")
    headers = {"Authorization": f"Bearer {guest['token']}"}
    assert client.get("/api/auth/me", headers=headers).json() == {"username": guest["username"], "guest": True}
    assert client.post("/api/worlds", json=SMALL, headers=headers).status_code == 200
    assert enter(client, guest["username"], "anything1234").status_code == 422  # a guest name is not a username


def test_playing_needs_a_signed_in_browser(client: TestClient) -> None:
    assert client.post("/api/worlds", json=SMALL).status_code == 401
    assert client.get("/api/worlds/abc").status_code == 401
    assert client.get("/api/accounts/shivam/days").status_code == 401
    assert client.post("/api/worlds", json=SMALL, headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_you_always_play_as_yourself_whatever_the_request_says(client: TestClient) -> None:
    mine = sign_up(client, "shivam")
    world = client.post("/api/worlds", json={**SMALL, "owner": "someone_else"}, headers=mine).json()
    assert world["owner"] == "shivam"


def test_nobody_can_touch_another_persons_day_or_history(client: TestClient) -> None:
    mine, theirs = sign_up(client, "shivam"), sign_up(client, "friend", "orange8080")
    world_id = client.post("/api/worlds", json=SMALL, headers=mine).json()["id"]
    assert client.get(f"/api/worlds/{world_id}", headers=mine).status_code == 200
    for call in (
        client.get(f"/api/worlds/{world_id}", headers=theirs),
        client.post(f"/api/worlds/{world_id}/advance", json={"seconds": 1}, headers=theirs),
        client.get(f"/api/worlds/{world_id}/statement", headers=theirs),
        client.delete(f"/api/worlds/{world_id}", headers=theirs),
    ):
        assert call.status_code == 404  # looks like no such day
    assert client.get("/api/accounts/shivam/days", headers=theirs).status_code == 403
    assert client.get("/api/accounts/shivam/days", headers=mine).status_code == 200


def test_signing_out_ends_the_token(client: TestClient) -> None:
    mine = sign_up(client, "shivam")
    assert client.get("/api/auth/me", headers=mine).status_code == 200
    client.post("/api/auth/logout", headers=mine)
    assert client.get("/api/auth/me", headers=mine).status_code == 401


def test_the_older_session_api_is_switched_off_when_login_is_on(client: TestClient) -> None:
    assert client.post("/api/sessions", json={}).status_code == 404


def test_the_database_holds_a_hash_not_the_secret(tmp_path: Any) -> None:
    import sqlite3

    path = str(tmp_path / "market.db")
    sign_up(TestClient(create_app(db_path=path, require_login=True)), "shivam")
    row = sqlite3.connect(path).execute("SELECT secret_hash FROM users").fetchone()[0]
    assert row.startswith("scrypt$") and "purple" not in row


def test_accounts_and_days_survive_a_restart(tmp_path: Any) -> None:
    path = str(tmp_path / "market.db")
    first = TestClient(create_app(db_path=path, require_login=True))
    sign_up(first, "shivam")
    second = TestClient(create_app(db_path=path, require_login=True))
    assert enter(second, "shivam", "purple4217").json()["status"] == "signed_in"
    assert enter(second, "shivam", "tiger7777").status_code == 401


def test_new_accounts_per_address_are_limited(client: TestClient) -> None:
    for n in range(30):
        assert client.post("/api/auth/guest").status_code == 200, n
    assert client.post("/api/auth/guest").status_code == 429
