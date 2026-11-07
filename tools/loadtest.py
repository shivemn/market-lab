"""Load test: many fake users playing a practice day at once, against the real API.

Each fake user does what the page does: start a day, then every second (--tick) ask the server to move the clock on
by (speed x tick) simulated seconds, and now and then place an order. We time every request and count failures.

    python tools/loadtest.py --url http://127.0.0.1:8100 --users 50 --seconds 30 --speed 1 --server-pid 1234

Run the client on a different machine from the server for a clean reading; on one machine they share the CPUs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time

import httpx

from marketlab.world import CATALOGUE

SYMBOLS = [c.symbol for c in CATALOGUE]


class Stats:
    def __init__(self) -> None:
        self.times: dict[str, list[float]] = {}
        self.errors: dict[str, int] = {}
        self.started_days = 0
        self.lost_days = 0

    def add(self, kind: str, seconds: float) -> None:
        self.times.setdefault(kind, []).append(seconds)

    def fail(self, kind: str, why: str) -> None:
        key = f"{kind}: {why}"
        self.errors[key] = self.errors.get(key, 0) + 1


async def user(
    n: int, client: httpx.AsyncClient, stats: Stats, args: argparse.Namespace, stop_at: float, tokens: dict[int, str]
) -> None:
    name = f"lt{n:05d}"
    headers = {"Authorization": f"Bearer {tokens[n]}"} if n in tokens else {}
    await asyncio.sleep(random.random() * args.ramp)  # people do not all arrive in the same millisecond
    t = time.perf_counter()
    try:
        r = await client.post("/api/worlds", json={"seed": n, "owner": name}, headers=headers)
        r.raise_for_status()
    except Exception as error:  # noqa: BLE001 - we count and carry on
        stats.fail("start", type(error).__name__)
        return
    stats.add("start", time.perf_counter() - t)
    stats.started_days += 1
    world = r.json()["id"]
    next_tick = time.perf_counter()
    last_order = time.perf_counter()
    while time.perf_counter() < stop_at:
        next_tick += args.tick
        t = time.perf_counter()
        try:
            body = {"seconds": args.speed * args.tick, "pause_on_fill": False}
            r = await client.post(f"/api/worlds/{world}/advance", json=body, headers=headers)
            if r.status_code == 404:
                stats.lost_days += 1
                stats.fail("advance", "404 day was evicted")
                return
            r.raise_for_status()
            stats.add("advance", time.perf_counter() - t)
            if (
                b'"finished":true' in r.content[-300:] or b'"finished":true' in r.content[:300]
            ):  # cheap check: no JSON parse
                return
        except Exception as error:  # noqa: BLE001
            stats.fail("advance", type(error).__name__)
        if time.perf_counter() - last_order > 6:
            last_order = time.perf_counter()
            t = time.perf_counter()
            try:
                r = await client.post(
                    f"/api/worlds/{world}/orders",
                    json={"symbol": random.choice(SYMBOLS), "side": random.choice(["BUY", "SELL"]), "quantity": 10},
                    headers=headers,
                )
                if r.status_code in (200, 422):  # 422 = refused by the exchange rules, a normal answer
                    stats.add("order", time.perf_counter() - t)
                else:
                    stats.fail("order", str(r.status_code))
            except Exception as error:  # noqa: BLE001
                stats.fail("order", type(error).__name__)
        await asyncio.sleep(max(0.0, next_tick - time.perf_counter()))  # a slow server makes the page fall behind


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * p))] * 1000


async def run(args: argparse.Namespace) -> dict[str, object]:
    proc = None
    if args.server_pid:
        import psutil

        proc = psutil.Process(args.server_pid)
        family = [proc, *proc.children(recursive=True)]  # a cluster is a router plus workers: count them all
        for each in family:
            each.cpu_percent(None)
    stats = Stats()
    tokens: dict[int, str] = {}
    if args.db:  # sign the fake users in directly in the database: the sign-in itself is not what is being measured
        from marketlab import accounts
        from marketlab.ledger import Ledger

        ledger = Ledger(args.db)
        for n in range(args.users):
            name = f"lt{n:05d}"
            ledger.create_user(name, None, guest=True)
            tokens[n] = accounts.new_token(name)
            ledger.add_login(accounts.token_hash(tokens[n]), name, days=1)
        ledger.close()
    limits = httpx.Limits(max_connections=args.users + 10, max_keepalive_connections=args.users + 10)
    async with httpx.AsyncClient(base_url=args.url, timeout=30, limits=limits) as client:
        begin = time.perf_counter()
        stop_at = begin + args.ramp + args.seconds
        await asyncio.gather(*(user(n, client, stats, args, stop_at, tokens) for n in range(args.users)))
        elapsed = time.perf_counter() - begin
    adv = stats.times.get("advance", [])
    out = {
        "users": args.users,
        "speed": args.speed,
        "seconds": round(elapsed, 1),
        "days_started": stats.started_days,
        "days_lost": stats.lost_days,
        "advance_requests": len(adv),
        "requests_per_s": round(len(adv) / elapsed, 1),
        "wanted_per_s": round(args.users / args.tick, 1),
        "advance_ms": {f"p{int(p * 100)}": round(pct(adv, p)) for p in (0.5, 0.95, 0.99)} if adv else None,
        "mean_ms": round(statistics.mean(adv) * 1000) if adv else None,
        "errors": stats.errors,
    }
    if proc:
        out["server_cpu_percent"] = round(sum(each.cpu_percent(None) for each in family))  # 100 = one core
        out["server_memory_mb"] = round(sum(each.memory_info().rss for each in family) / 1e6)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8100")
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--seconds", type=float, default=30, help="how long each user plays after arriving")
    parser.add_argument("--ramp", type=float, default=5, help="users arrive spread over this many seconds")
    parser.add_argument("--speed", type=float, default=1, help="playback speed the fake users choose (1, 4, 10 ...)")
    parser.add_argument("--tick", type=float, default=1.0, help="how often a page asks, in seconds (the page uses 1.0)")
    parser.add_argument(
        "--db",
        default="",
        help="the server's postgresql:// address; fake users are signed in there (needed when sign-in is on)",
    )
    parser.add_argument("--server-pid", type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), indent=2))


if __name__ == "__main__":
    main()
