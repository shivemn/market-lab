"""The command line: run a simulation, look inside a log, and check that a log can be reproduced.

    marketlab run --seed 7 --out runs/demo.jsonl
    marketlab show runs/demo.jsonl --until 500 --events 10
    marketlab replay runs/demo.jsonl
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from marketlab.core import Side
from marketlab.describe import describe, money
from marketlab.log import EventLog, LogError, read_log, write_log
from marketlab.projection import MarketState
from marketlab.sim import SimConfig, run_simulation


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except LogError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="marketlab", description="A small simulated stock exchange.")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="simulate a trading day and write the event log")
    run.add_argument("--seed", type=int, default=1, help="the random seed; the same seed gives the same day")
    run.add_argument("--open-seconds", type=int, default=600, help="length of continuous trading, in simulated seconds")
    run.add_argument("--pre-open-seconds", type=int, default=60)
    run.add_argument("--noise-traders", type=int, default=20)
    run.add_argument("--out", type=Path, required=True, help="where to write the log (a .jsonl file)")
    run.set_defaults(handler=_run)

    show = commands.add_parser("show", help="read a log, check it, and show the market after N events")
    show.add_argument("log", type=Path)
    show.add_argument("--until", type=int, default=None, help="stop after this many events (default: all)")
    show.add_argument("--events", type=int, default=0, help="also print the last K events up to that point")
    show.add_argument("--levels", type=int, default=5, help="price levels to show on each side")
    show.set_defaults(handler=_show)

    replay = commands.add_parser("replay", help="re-run a simulated log from its seed and check it matches")
    replay.add_argument("log", type=Path)
    replay.set_defaults(handler=_replay)
    return parser


def _run(args: argparse.Namespace) -> int:
    config = SimConfig(
        seed=args.seed,
        open_seconds=args.open_seconds,
        pre_open_seconds=args.pre_open_seconds,
        noise_traders=args.noise_traders,
    )
    result = run_simulation(config)
    write_log(args.out, result.instrument, result.events, config.to_dict())
    state = result.state
    print(f"wrote {len(result.events)} events to {args.out}")
    print(f"fingerprint {result.sha256}")
    print(_summary(state))
    return 0


def _show(args: argparse.Namespace) -> int:
    log = read_log(args.log)
    count = len(log.events) if args.until is None else max(0, min(args.until, len(log.events)))
    state = MarketState(log.instrument)
    state.apply_all(log.events[:count])
    print(f"{args.log}: {len(log.events)} events, fingerprint {log.sha256} (checked)")
    if log.skipped_unknown:
        print(f"note: {log.skipped_unknown} events of an unknown type were skipped")
    print(f"showing the market after {count} events")
    print(_summary(state))
    print(_book(state, args.levels))
    if args.events > 0:
        print("\nlast events:")
        for event in log.events[max(0, count - args.events) : count]:
            print("  " + describe(event))
    kinds = Counter(type(event).__name__ for event in log.events[:count])
    print("\nevent counts: " + ", ".join(f"{name} {n}" for name, n in sorted(kinds.items())))
    return 0


def _replay(args: argparse.Namespace) -> int:
    log = read_log(args.log)
    if log.simulation is None:
        print("this log has no simulation settings in its header, so it cannot be re-run")
        return 2
    config = SimConfig.from_dict(log.simulation)
    result = run_simulation(config)
    return _compare(log, result.sha256, len(result.events))


def _compare(log: EventLog, new_sha: str, new_count: int) -> int:
    if new_sha == log.sha256 and new_count == len(log.events):
        print(f"reproduced exactly: {new_count} events, fingerprint {new_sha}")
        return 0
    print(f"DIFFERENT: the log has {len(log.events)} events ({log.sha256}), the re-run has {new_count} ({new_sha})")
    return 1


def _summary(state: MarketState) -> str:
    def price(value: int | None) -> str:
        return "-" if value is None else money(value)

    return (
        f"session {state.session.value}, opening {price(state.opening_price)}, last {price(state.last_price)}, "
        f"high {price(state.high)}, low {price(state.low)}, {state.trades} trades, {state.volume} shares"
    )


def _book(state: MarketState, levels: int) -> str:
    asks = state.depth(Side.SELL, levels)
    bids = state.depth(Side.BUY, levels)
    lines = ["", "      price    shares  orders"]
    for level in reversed(asks):
        lines.append(f"ask {money(level.price):>10} {level.quantity:>9} {level.orders:>7}")
    lines.append("    ----------------------------")
    for level in bids:
        lines.append(f"bid {money(level.price):>10} {level.quantity:>9} {level.orders:>7}")
    return "\n".join(lines)
