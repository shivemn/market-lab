"""The router in front of several servers: who goes where, and what it passes on."""

from __future__ import annotations

import asyncio
import os
import secrets
import socket
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from marketlab import accounts
from marketlab.cluster import create_router, worker_for


def test_the_same_name_always_gets_the_same_worker_in_any_capitals() -> None:
    assert {worker_for("Shivam", 4) for _ in range(5)} == {worker_for("shivam", 4)}
    assert all(0 <= worker_for(f"user{n}", 3) < 3 for n in range(100))


def test_names_spread_over_the_workers() -> None:
    spread = Counter(worker_for(f"player{n}", 4) for n in range(2000))
    assert set(spread) == {0, 1, 2, 3}
    assert all(350 < count < 650 for count in spread.values())  # about 500 each


def fake_worker(index: int) -> FastAPI:
    app = FastAPI()

    @app.api_route("/{path:path}", methods=["GET", "POST"])
    async def anything(request: Request, path: str) -> dict[str, Any]:
        reply: dict[str, Any] = {
            "worker": index,
            "path": request.url.path,
            "forwarded_for": request.headers.get("x-forwarded-for"),
            "query": str(request.url.query),
        }
        if request.url.path == "/api/runs" and request.method == "POST":
            reply["id"] = secrets.token_hex(6)
        return reply

    return app


@pytest.fixture
def router() -> TestClient:
    transports = [httpx.ASGITransport(app=fake_worker(i)) for i in range(3)]
    return TestClient(create_router([9001, 9002, 9003], transports=transports))


def signed_in(name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {accounts.new_token(name)}"}


def test_every_request_of_a_person_goes_to_one_worker_even_with_new_tokens(router: TestClient) -> None:
    for name in ("alice", "bob", "carol", "guest-ab12cd"):
        seen = {router.get("/api/worlds/x", headers=signed_in(name)).json()["worker"] for _ in range(6)}
        assert seen == {worker_for(name, 3)}  # six requests, six different tokens, one worker


def test_capitals_in_the_name_do_not_change_the_worker(router: TestClient) -> None:
    low = router.get("/api/x", headers=signed_in("shivam")).json()["worker"]
    assert router.get("/api/x", headers=signed_in("SHIVAM")).json()["worker"] == low


def test_requests_with_nothing_to_tie_them_take_turns(router: TestClient) -> None:
    workers = [router.get("/api/config").json()["worker"] for _ in range(6)]
    assert workers == [0, 1, 2, 0, 1, 2]


def test_a_run_is_followed_back_to_the_worker_that_made_it(router: TestClient) -> None:
    for _ in range(7):
        made = router.post("/api/runs", json={}).json()
        again = {router.get(f"/api/runs/{made['id']}/events").json()["worker"] for _ in range(3)}
        assert again == {made["worker"]}


def test_the_query_and_path_are_passed_on_untouched(router: TestClient) -> None:
    reply = router.get("/api/runs/abc/events?after=5&limit=10").json()
    assert reply["path"] == "/api/runs/abc/events" and reply["query"] == "after=5&limit=10"


def test_the_worker_is_told_the_real_client_address(router: TestClient) -> None:
    assert router.get("/api/x").json()["forwarded_for"] == "testclient"  # whatever the client claims is ignored
    lying = router.get("/api/x", headers={"X-Forwarded-For": "6.6.6.6"}).json()["forwarded_for"]
    assert lying == "testclient"


def test_behind_a_trusted_proxy_the_first_forwarded_address_is_the_visitor() -> None:
    transports = [httpx.ASGITransport(app=fake_worker(0))]
    behind = TestClient(create_router([9001], behind_proxy=True, transports=transports))
    seen = behind.get("/api/x", headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.2"}).json()["forwarded_for"]
    assert seen == "203.0.113.9"


def test_a_worker_that_is_down_gives_a_plain_message_not_a_crash() -> None:
    class Down(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

    down = TestClient(create_router([9001], transports=[Down()]))
    reply = down.get("/api/x")
    assert reply.status_code == 502 and "restarting" in reply.json()["detail"]


# -- the real thing: two workers and a router, on PostgreSQL ----------------------------------------------------

PG_URL = os.environ.get("MARKETLAB_TEST_PG")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def cluster() -> Iterator[str]:
    import psycopg

    assert PG_URL
    schema = "c" + secrets.token_hex(5)
    with psycopg.connect(PG_URL, autocommit=True) as setup:
        setup.execute(f"CREATE SCHEMA {schema}")
    sep = "&" if "?" in PG_URL else "?"
    url = f"{PG_URL}{sep}options={quote(f'-c search_path={schema}')}"
    port = free_port()
    while free_port() in (port + 1, port + 2):  # the workers use the next two ports
        port = free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "marketlab", "cluster", "--workers", "2", "--port", str(port), "--db", url]
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{base}/api/config", timeout=2).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.3)
        else:
            raise RuntimeError("the cluster did not start")
        yield base
    finally:
        process.terminate()
        process.wait(timeout=20)


@pytest.mark.skipif(not PG_URL, reason="needs PostgreSQL: set MARKETLAB_TEST_PG")
def test_two_real_workers_serve_whole_days_and_keep_each_person_on_their_own(cluster: str) -> None:
    import websockets

    client = httpx.Client(base_url=cluster, timeout=30)
    people = {}
    for name in ("amy", "ben", "cat", "dev", "eli", "fay"):
        entered = client.post("/api/auth/enter", json={"username": name, "secret": "purple4217", "create": True})
        assert entered.status_code == 200, entered.text
        people[name] = {"Authorization": f"Bearer {entered.json()['token']}"}
    assert {worker_for(n, 2) for n in people} == {0, 1}  # the six really are split over both workers
    days = {}
    for name, headers in people.items():
        started = client.post(
            "/api/worlds", json={"seed": 3, "open_seconds": 60, "pre_open_seconds": 10}, headers=headers
        )
        assert started.status_code == 200, started.text
        wid = started.json()["id"]
        days[name] = wid
        for _ in range(4):
            moved = client.post(
                f"/api/worlds/{wid}/advance", json={"seconds": 3, "pause_on_fill": False}, headers=headers
            )
            assert moved.status_code == 200, moved.text
        audit = client.get(f"/api/worlds/{wid}/statement", headers=headers).json()
        assert audit["problems"] == []  # every person's books are sound in the shared database
    assert client.get(f"/api/worlds/{days['amy']}", headers=people["ben"]).status_code == 404
    second_browser = client.post("/api/auth/enter", json={"username": "amy", "secret": "purple4217"}).json()
    again = {"Authorization": f"Bearer {second_browser['token']}"}
    assert client.get(f"/api/worlds/{days['amy']}", headers=again).status_code == 200  # same worker, same day
    run = client.post("/api/runs", json={"seed": 9, "open_seconds": 20, "pre_open_seconds": 5}).json()

    async def watch() -> int:
        url = cluster.replace("http", "ws") + f"/ws/runs/{run['id']}?speed=100"
        async with websockets.connect(url) as socket_:
            count = 0
            async for _ in socket_:
                count += 1
                if count >= 3:
                    break
            return count

    assert asyncio.run(watch()) == 3  # the live stream is relayed through the router
