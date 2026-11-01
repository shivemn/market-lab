"""Writes web/src/fixtures/day.json: events plus the market as the Python code sees it at command boundaries.

The dashboard has its own copy of the "fold events into a market picture" logic (in TypeScript). Its tests load this
file and check that the TypeScript copy gives exactly the same picture as the Python one. Run from the project folder:

    python -m tests.export_fixture
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from marketlab.api.app import state_json
from marketlab.codec import event_to_dict
from marketlab.core import AuctionResult, Event, SessionChanged
from marketlab.projection import MarketState, command_ends
from marketlab.sim import SimConfig, run_simulation
from tests.helpers import DEMO
from tests.unit.scenario import scripted_day

OUT = Path("web/src/fixtures/day.json")


def case(name: str, events: list[Event], every: int) -> dict[str, Any]:
    ends = command_ends(events)
    state = MarketState(DEMO)
    checks: list[dict[str, Any]] = []
    previous = 0
    for number, end in enumerate(ends):
        state.apply_all(events[previous:end])
        previous = end
        if number % every == 0 or end == len(events):
            checks.append(state_json(state))
    return {"name": name, "events": [event_to_dict(e) for e in events], "ends": ends, "states": checks}


def build() -> dict[str, Any]:
    scripted, _ = scripted_day()
    simulated = run_simulation(SimConfig(seed=5, pre_open_seconds=15, open_seconds=60, noise_traders=8)).events
    return {
        "cases": [case("scripted day", scripted, 1), case("simulated day, seed 5", simulated, 7)],
        "auctions": auctions(),
    }


def auctions() -> list[dict[str, Any]]:
    """Many small mornings: just the events up to the opening, with the exchange's own answer, so the dashboard's
    auction calculation can be checked against the exchange on many different order books."""
    found: list[dict[str, Any]] = []
    for seed in range(1, 41):
        config = SimConfig(seed=seed, pre_open_seconds=10 + seed % 20, open_seconds=10, noise_traders=3 + seed % 25)
        events = run_simulation(config).events
        end = next(i for i, e in enumerate(events) if isinstance(e, AuctionResult))
        stop = next(i for i, e in enumerate(events) if i > end and isinstance(e, SessionChanged)) + 1
        result = events[end]
        assert isinstance(result, AuctionResult)
        found.append(
            {
                "seed": seed,
                "events": [event_to_dict(e) for e in events[:stop]],
                "price": result.price,
                "volume": result.volume,
            }
        )
    return found


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
