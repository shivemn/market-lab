"""How fast is the matching engine? An honest measurement, not a marketing number.

Run from the project folder:

    python -m benchmarks.bench_exchange                # the full run (about a minute)
    python -m benchmarks.bench_exchange --quick        # a small run, for a quick look
    python -m benchmarks.bench_exchange --markdown docs/benchmark-results.md

What is measured: the exchange core only (`Exchange.submit`), one thread, no network, no log file, no Python-level
profiling. Two things are measured:

1. Mixed flow: a repeatable stream of limit orders (most passive, some crossing the spread), market orders and
   cancels, roughly in the proportions of a busy day. Reported as orders per second (timed as one block) and as the
   time each single command takes
   (percentiles, timed command by command, which adds a little overhead of its own).
2. Depth: how the cost of one command changes as the book holds more resting orders (1,000 up to 100,000). A good
   order book should not slow down as it fills.

Each measurement is repeated and the median is reported with the lowest and highest, because a single run on a
shared computer is not trustworthy. The numbers depend on this machine, this Python version and what else was
running. They say how the code scales; they do not predict how it would do on other hardware.
"""

from __future__ import annotations

import argparse
import gc
import json
import platform
import random
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from marketlab.core import (
    CancelOrder,
    Command,
    Exchange,
    Instrument,
    NewOrder,
    Order,
    OrderType,
    Session,
    Side,
    TimeInForce,
    Trade,
)

INSTRUMENT = Instrument(symbol="BENCH", tick_size=5, lot_size=1, reference_price=250_000, band_pct=20)

# A command described as plain data, so every run builds fresh Order objects (the exchange changes them as it goes).
Spec = tuple[str, int, Side, int | None, int, TimeInForce]  # kind, id, side, price, quantity, tif


def build(spec: Spec) -> Command:
    kind, order_id, side, price, quantity, tif = spec
    if kind == "C":
        return CancelOrder(order_id)
    order_type = OrderType.MARKET if kind == "M" else OrderType.LIMIT
    return NewOrder(Order(order_id, "BENCH", INSTRUMENT.symbol, side, order_type, quantity, price, tif, 0))


def generate(count: int, seed: int) -> list[Spec]:
    """A repeatable stream: about 45% passive limit orders, 15% crossing, 10% market orders, 30% cancels."""
    rng = random.Random(seed)
    exchange = Exchange(INSTRUMENT, Session.OPEN)
    tick = INSTRUMENT.tick_size
    live: list[int] = []
    specs: list[Spec] = []
    mid = INSTRUMENT.reference_price
    next_id = 0
    for number in range(count):
        roll = rng.random()
        command: Command
        if roll < 0.30 and live:
            index = rng.randrange(len(live))
            live[index], live[-1] = live[-1], live[index]
            victim = live.pop()
            if victim not in exchange.book:
                continue  # already traded away: pick again next time
            specs.append(("C", victim, Side.BUY, None, 0, TimeInForce.DAY))
            command = CancelOrder(victim)
        else:
            next_id += 1
            side = Side.BUY if rng.random() < 0.5 else Side.SELL
            quantity = rng.randint(1, 100)
            if roll < 0.40:
                spec: Spec = ("M", next_id, side, None, quantity, TimeInForce.IOC)
            elif roll < 0.55:
                reach = rng.randint(0, 3) * tick
                price = mid + reach if side is Side.BUY else mid - reach
                spec = ("L", next_id, side, _clamp(price), quantity, TimeInForce.DAY)
            else:
                away = rng.randint(1, 30) * tick
                price = mid - away if side is Side.BUY else mid + away
                spec = ("L", next_id, side, _clamp(price), quantity, TimeInForce.DAY)
            specs.append(spec)
            command = build(spec)
            if spec[0] == "L":
                live.append(next_id)
        events = exchange.submit(command, number + 1)
        for event in events:
            if isinstance(event, Trade):
                mid = event.price
    return specs


def _clamp(price: int) -> int:
    return min(max(price, INSTRUMENT.band_low), INSTRUMENT.band_high)


def run_block(specs: list[Spec]) -> float:
    """Seconds to process every command, timed as one block."""
    commands = [build(spec) for spec in specs]
    exchange = Exchange(INSTRUMENT, Session.OPEN)
    submit = exchange.submit
    gc.collect()
    start = time.perf_counter()
    for number, command in enumerate(commands, start=1):
        submit(command, number)
    return time.perf_counter() - start


def run_each(specs: list[Spec]) -> list[int]:
    """Nanoseconds taken by each single command."""
    commands = [build(spec) for spec in specs]
    exchange = Exchange(INSTRUMENT, Session.OPEN)
    submit = exchange.submit
    clock = time.perf_counter_ns
    taken: list[int] = []
    gc.collect()
    for number, command in enumerate(commands, start=1):
        began = clock()
        submit(command, number)
        taken.append(clock() - began)
    return taken


def percentile(sorted_values: list[int], fraction: float) -> int:
    return sorted_values[min(len(sorted_values) - 1, int(fraction * len(sorted_values)))]


@dataclass
class Spread:
    median: float
    low: float
    high: float

    @staticmethod
    def of(values: list[float]) -> Spread:
        return Spread(statistics.median(values), min(values), max(values))


def mixed_flow(count: int, repeats: int) -> dict[str, Any]:
    specs = generate(count, seed=1)
    run_block(specs[: min(2000, len(specs))])  # warm-up, discarded
    seconds = [run_block(specs) for _ in range(repeats)]
    per_second = Spread.of([len(specs) / s for s in seconds])
    each = sorted(run_each(specs))
    kinds = [spec[0] for spec in specs]
    return {
        "commands": len(specs),
        "mix": {
            "limit": kinds.count("L") / len(kinds),
            "market": kinds.count("M") / len(kinds),
            "cancel": kinds.count("C") / len(kinds),
        },
        "repeats": repeats,
        "commands_per_second": {"median": per_second.median, "low": per_second.low, "high": per_second.high},
        "latency_ns": {
            "p50": percentile(each, 0.50),
            "p90": percentile(each, 0.90),
            "p99": percentile(each, 0.99),
            "p999": percentile(each, 0.999),
            "max": each[-1],
        },
    }


def filled_book(depth: int) -> tuple[Exchange, int]:
    """An exchange whose book holds `depth` resting orders, half buys and half sells, over many price levels."""
    rng = random.Random(7)
    exchange = Exchange(INSTRUMENT, Session.OPEN)
    tick = INSTRUMENT.tick_size
    mid = INSTRUMENT.reference_price
    levels = max(1, min(depth // 5, 8_000))
    for order_id in range(1, depth + 1):
        side = Side.BUY if order_id % 2 else Side.SELL
        away = (rng.randrange(levels) + 5) * tick
        price = mid - away if side is Side.BUY else mid + away
        price = _clamp(price)
        spec: Spec = ("L", order_id, side, price, rng.randint(1, 100), TimeInForce.DAY)
        exchange.submit(build(spec), order_id)
    assert len(exchange.book) == depth, "the benchmark book did not fill as planned"
    return exchange, depth


def depth_costs(depths: list[int], operations: int, repeats: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for depth in depths:
        medians: dict[str, list[float]] = {"rest and cancel": [], "market order": []}
        for _ in range(repeats):
            exchange, last_id = filled_book(depth)
            rng = random.Random(depth)
            tick = INSTRUMENT.tick_size
            mid = INSTRUMENT.reference_price
            clock = time.perf_counter_ns
            gc.collect()
            now = depth
            # (a) a passive order near the middle goes on the book and is cancelled again
            taken: list[int] = []
            for _ in range(operations):
                last_id += 1
                now += 1
                price = mid - (rng.randint(1, 4_000) * tick)
                order = build(("L", last_id, Side.BUY, _clamp(price), 10, TimeInForce.DAY))
                cancel = CancelOrder(last_id)
                began = clock()
                exchange.submit(order, now)
                now += 1
                exchange.submit(cancel, now)
                taken.append(clock() - began)
            medians["rest and cancel"].append(statistics.median(taken) / 2)
            # (b) a small market order trades against the best price, and a new order refills the book
            taken = []
            for _ in range(operations):
                last_id += 1
                now += 1
                market = build(("M", last_id, Side.BUY, None, 1, TimeInForce.IOC))
                began = clock()
                exchange.submit(market, now)
                taken.append(clock() - began)
                last_id += 1
                now += 1
                refill_price = mid + (rng.randint(5, 4_000) * tick)
                exchange.submit(build(("L", last_id, Side.SELL, _clamp(refill_price), 5, TimeInForce.DAY)), now)
            medians["market order"].append(statistics.median(taken))
        rows.append(
            {
                "depth": depth,
                "rest_and_cancel_ns": Spread.of(medians["rest and cancel"]).median,
                "market_order_ns": Spread.of(medians["market order"]).median,
            }
        )
    return rows


def machine() -> dict[str, str]:
    cpu = platform.processor() or platform.machine()
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "cpu": cpu,
        "os": platform.system(),
    }


def to_markdown(result: dict[str, Any]) -> str:
    flow = result["mixed_flow"]
    rate, lat = flow["commands_per_second"], flow["latency_ns"]
    lines = [
        "## Mixed order flow",
        "",
        f"{flow['commands']:,} commands ({flow['mix']['limit']:.0%} limit orders, some passive and some crossing "
        f"the spread; {flow['mix']['market']:.0%} market orders; {flow['mix']['cancel']:.0%} cancels), "
        f"repeated {flow['repeats']} times.",
        "",
        f"- **Throughput:** {rate['median']:,.0f} commands per second "
        f"(lowest run {rate['low']:,.0f}, highest {rate['high']:,.0f})",
        "- **Time per command:** "
        f"median {lat['p50'] / 1000:.1f} µs, 90th percentile {lat['p90'] / 1000:.1f} µs, "
        f"99th {lat['p99'] / 1000:.1f} µs, 99.9th {lat['p999'] / 1000:.1f} µs, slowest {lat['max'] / 1000:.0f} µs",
        "",
        "## Does it slow down as the book fills up?",
        "",
        "| Orders resting on the book | Rest a new order and cancel it (per command) "
        "| Market order that trades (per command) |",
        "|---:|---:|---:|",
    ]
    for row in result["depth"]:
        lines.append(
            f"| {row['depth']:,} | {row['rest_and_cancel_ns'] / 1000:.1f} µs | {row['market_order_ns'] / 1000:.1f} µs |"
        )
    m = result["machine"]
    lines += [
        "",
        f"Measured on: {m['cpu']}, {m['implementation']} {m['python']}, {m['os']}.",
    ]
    return "\n".join(lines) + "\n"


def run(quick: bool, progress: Callable[[str], None] = print) -> dict[str, Any]:
    count, repeats = (5_000, 3) if quick else (200_000, 5)
    depths = [200, 1_000, 5_000] if quick else [1_000, 10_000, 100_000]
    operations = 500 if quick else 5_000
    progress(f"mixed flow: {count:,} commands x {repeats} runs ...")
    flow = mixed_flow(count, repeats)
    progress("book depth ...")
    return {"machine": machine(), "mixed_flow": flow, "depth": depth_costs(depths, operations, 3 if not quick else 2)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure the exchange core.")
    parser.add_argument("--quick", action="store_true", help="a small, fast run")
    parser.add_argument("--markdown", type=Path, help="also write the results as a Markdown file")
    parser.add_argument("--json", type=Path, help="also write the raw results as JSON")
    args = parser.parse_args()
    result = run(args.quick)
    text = to_markdown(result)
    print()
    print(text)
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(text, encoding="utf-8", newline="\n")
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
