"""The command line: run a simulation, look inside a log, and check that a log can be reproduced.

marketlab run --seed 7 --out runs/demo.jsonl
marketlab show runs/demo.jsonl --until 500 --events 10
marketlab replay runs/demo.jsonl
marketlab serve
marketlab costs --side buy --quantity 100 --price 2500
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from marketlab.core import Side
from marketlab.costs import PLANS, CostModel, schedule_on
from marketlab.describe import describe, money
from marketlab.log import EventLog, LogError, read_log, write_log
from marketlab.projection import MarketState, command_ends
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

    serve = commands.add_parser("serve", help="start the web server (the live dashboard talks to it)")
    serve.add_argument("--host", default="127.0.0.1", help="keep the default unless you know why you are changing it")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--web", type=Path, default=Path("web/dist"), help="the built dashboard, if you have built it")
    serve.set_defaults(handler=_serve)

    costs = commands.add_parser("costs", help="what a delivery trade would cost, line by line")
    costs.add_argument("--side", choices=["buy", "sell"], required=True)
    costs.add_argument("--quantity", type=int, required=True, help="number of shares")
    costs.add_argument("--price", type=float, required=True, help="price per share, in rupees")
    costs.add_argument("--plan", choices=sorted(PLANS), default="zero", help="the broker's own charges")
    costs.add_argument("--date", type=date.fromisoformat, default=None, help="trading day, YYYY-MM-DD (default: today)")
    costs.set_defaults(handler=_costs)

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


def _serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn

        from marketlab.api import create_app
    except ImportError:
        print('error: the web server needs extra packages. Run:  pip install -e ".[api]"', file=sys.stderr)
        return 2
    web = args.web if args.web.is_dir() else None
    dashboard = "built" if web else "not built, use npm run dev"
    print(f"Market Lab server on http://{args.host}:{args.port}  (dashboard: {dashboard})")
    uvicorn.run(create_app(web), host=args.host, port=args.port, log_level="warning")
    return 0


def _show(args: argparse.Namespace) -> int:
    log = read_log(args.log)
    wanted = len(log.events) if args.until is None else max(0, min(args.until, len(log.events)))
    # Stop at the end of a finished command, never in the middle of one (see projection.command_ends).
    count = max((end for end in command_ends(log.events) if end <= wanted), default=0)
    state = MarketState(log.instrument)
    state.apply_all(log.events[:count])
    print(f"{args.log}: {len(log.events)} events, fingerprint {log.sha256} (checked)")
    if log.skipped_unknown:
        print(f"note: {log.skipped_unknown} events of an unknown type were skipped")
    note = f" (you asked for {wanted}; event {wanted} is in the middle of a command)" if count != wanted else ""
    print(f"showing the market after {count} events{note}")
    print(_summary(state))
    print(_book(state, args.levels))
    if args.events > 0:
        print("\nlast events:")
        for event in log.events[max(0, count - args.events) : count]:
            print("  " + describe(event))
    kinds = Counter(type(event).__name__ for event in log.events[:count])
    print("\nevent counts: " + ", ".join(f"{name} {n}" for name, n in sorted(kinds.items())))
    return 0


def _costs(args: argparse.Namespace) -> int:
    if args.quantity <= 0 or args.price <= 0:
        raise ValueError("quantity and price must be positive")
    paise = round(args.price * 100)
    if abs(paise - args.price * 100) > 1e-6:
        raise ValueError("price must be in whole paise, for example 2500.05")
    side = Side.BUY if args.side == "buy" else Side.SELL
    day = args.date or date.today()
    model = CostModel(schedule_on(day), PLANS[args.plan])
    value = paise * args.quantity
    breakdown = model.for_order(side, value)
    names = {
        "brokerage": "Brokerage",
        "stt": "Securities transaction tax",
        "exchange": "Exchange transaction charge",
        "sebi": "SEBI turnover fee",
        "stamp": "Stamp duty",
        "demat": "Demat fee",
        "gst": "GST",
    }
    print(f"{args.side.capitalize()} {args.quantity} shares at {money(paise)}   (charges in force on {day})")
    print(f"  Value of the trade                  {money(value):>14}")
    for line, amount in breakdown.lines():
        if amount:
            print(f"  {names[line]:<35} {money(amount):>14}")
    print(f"  {'Total charges':<35} {money(breakdown.total):>14}")
    print(f"  That is {breakdown.total * 100 / value:.3f}% of the trade's value.")
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
