"""Several server processes behind one address, with each person always sent to the same one.

Why "always the same one": a practice day lives in the memory of the process that started it. Money, accounts and
history are in the shared database, but the day in progress is not, so a person's requests must keep reaching the
process that holds their day. The router decides by the name at the front of the sign-in token (`shivam.k3j...`):
the same name always gives the same worker number.

    marketlab cluster --workers 4 --db postgresql://user:password@host/database

The router is deliberately small. It forwards requests and relays the WebSocket the "Watch a day" screen uses; it does
not look inside anything else. Workers listen on the loopback address only, and the router tells each one the real
client address (X-Forwarded-For) so the sign-in limits still count per visitor.
"""

from __future__ import annotations

import asyncio
import itertools
import os
import re
import signal
import subprocess
import sys
import threading
import time
import zlib
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import websockets
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect

from marketlab.accounts import token_owner

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    "content-encoding",
    "accept-encoding",
}
RUN_PATH = re.compile(r"^/(?:api|ws)/runs/([0-9A-Za-z]+)")
MAX_RUNS_REMEMBERED = 2000


def worker_for(key: str, workers: int) -> int:
    """The same key (in any capitals) always gives the same worker number."""
    return zlib.crc32(key.lower().encode()) % workers


def bearer(headers: Any) -> str:
    scheme, _, token = (headers.get("authorization") or "").partition(" ")
    return token if scheme.lower() == "bearer" else ""


def create_router(ports: list[int], *, behind_proxy: bool = False, transports: list[Any] | None = None) -> Any:
    """The ASGI app in front of the workers listening on `ports`. A test can stand in for them with `transports`."""
    count = len(ports)
    clients = [
        httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}",
            transport=None if transports is None else transports[i],
            timeout=60,
            limits=httpx.Limits(max_connections=400, max_keepalive_connections=100),
        )
        for i, port in enumerate(ports)
    ]

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        for client in clients:
            await client.aclose()

    app = FastAPI(title="Market Lab router", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    spin = itertools.count()
    run_home: OrderedDict[str, int] = OrderedDict()  # which worker made a run, so its later requests go back there

    def choose(path: str, headers: Any) -> int:
        owner = token_owner(bearer(headers))
        if owner:
            return worker_for(owner, count)
        found = RUN_PATH.match(path)
        if found and found.group(1) in run_home:
            return run_home[found.group(1)]
        return next(spin) % count  # nothing ties this request to a worker: any will do

    def client_address(headers: Any, direct: str) -> str:
        if behind_proxy and headers.get("x-forwarded-for"):
            return str(headers["x-forwarded-for"]).split(",")[0].strip()
        return direct

    @app.websocket("/ws/{rest:path}")
    async def relay(client: WebSocket, rest: str) -> None:
        index = choose(client.url.path, client.headers)
        query = f"?{client.url.query}" if client.url.query else ""
        try:
            async with websockets.connect(f"ws://127.0.0.1:{ports[index]}/ws/{rest}{query}") as upstream:
                await client.accept()

                async def down() -> None:
                    async for message in upstream:
                        if isinstance(message, bytes):
                            await client.send_bytes(message)
                        else:
                            await client.send_text(message)

                async def up() -> None:
                    try:
                        while True:
                            await upstream.send(await client.receive_text())
                    except WebSocketDisconnect:
                        pass

                done, pending = await asyncio.wait(
                    {asyncio.ensure_future(down()), asyncio.ensure_future(up())}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
        except (OSError, websockets.WebSocketException):
            await client.close(code=1011)
            return
        try:
            await client.close()
        except RuntimeError:
            pass  # already closed

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
    async def forward(request: Request, path: str) -> Response:
        index = choose(request.url.path, request.headers)
        headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP}
        direct = request.client.host if request.client else "unknown"
        headers["x-forwarded-for"] = client_address(request.headers, direct)
        try:
            reply = await clients[index].request(
                request.method,
                request.url.path + (f"?{request.url.query}" if request.url.query else ""),
                headers=headers,
                content=await request.body(),
            )
        except httpx.TransportError:
            return Response(
                '{"detail":"The server is restarting. Try again in a moment."}',
                status_code=502,
                media_type="application/json",
            )
        if request.method == "POST" and request.url.path == "/api/runs" and reply.status_code == 200:
            try:
                run_home[str(reply.json()["id"])] = index
                while len(run_home) > MAX_RUNS_REMEMBERED:
                    run_home.popitem(last=False)
            except (ValueError, KeyError):
                pass
        out = {k: v for k, v in reply.headers.items() if k.lower() not in HOP_BY_HOP}
        return Response(reply.content, status_code=reply.status_code, headers=out)

    return app


# -- starting and watching the workers -------------------------------------------------------------------------


def _spawn(index: int, port: int, db: str, web: Path, no_login: bool) -> subprocess.Popen[bytes]:
    """Start one worker. It is told its parent's process number, so it stops by itself if the router vanishes."""
    command = [
        sys.executable,
        "-m",
        "marketlab",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--db",
        db,
        "--web",
        str(web),
        "--behind-proxy",  # the router sends the real client address
        "--parent-pid",
        str(os.getpid()),
    ]
    if no_login:
        command.append("--no-login")
    return subprocess.Popen(command)


def _wait_ready(ports: list[int], seconds: float = 60) -> None:
    deadline = time.monotonic() + seconds
    for port in ports:
        while True:
            try:
                if httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=2).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError(f"the worker on port {port} did not start within {seconds:.0f} seconds")
            time.sleep(0.3)


def run_cluster(
    *, workers: int, host: str, port: int, db: str, web: Path, no_login: bool = False, behind_proxy: bool = False
) -> None:
    import uvicorn

    ports = [port + 1 + i for i in range(workers)]
    processes = [_spawn(i, p, db, web, no_login) for i, p in enumerate(ports)]
    stop = threading.Event()

    def keep_alive() -> None:
        """A worker that dies is started again. The days it held are lost, as in any restart; accounts are safe."""
        while not stop.wait(1.0):
            for i, process in enumerate(processes):
                if process.poll() is not None:
                    print(f"worker {i} stopped (exit {process.returncode}); starting it again", flush=True)
                    processes[i] = _spawn(i, ports[i], db, web, no_login)

    def shut_down(signum: int, _frame: Any) -> None:
        """Uvicorn, on being stopped, finishes its own shutdown and then re-sends the signal to the process, which
        would end it without running the `finally` below. Stopping the workers here, first, is what prevents orphans."""
        stop.set()
        for process in processes:
            process.terminate()
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    for name in ("SIGTERM", "SIGINT"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), shut_down)
    try:
        _wait_ready(ports)
        threading.Thread(target=keep_alive, daemon=True).start()
        print(f"Market Lab router on http://{host}:{port}  ({workers} workers on ports {ports[0]}-{ports[-1]})")
        uvicorn.run(
            create_router(ports, behind_proxy=behind_proxy),
            host=host,
            port=port,
            log_level="warning",
            proxy_headers=behind_proxy,
            forwarded_allow_ips="*" if behind_proxy else None,
        )
    finally:
        stop.set()
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
