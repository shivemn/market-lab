"""Possible prices at the close, for the price-paths panel (the Galton board on the Practice screen).

Each run starts from the company's last traded price, never from the hidden fair value that the simulated traders
react to, so the panel gives the player no edge over them. It moves forward with the same process the simulator uses
(`FairValue`: geometric Brownian motion with rare jumps), with the company's whole volatility: its share of the
market move (beta times the market's), its sector's move, and its own. News that has not come out yet is not known,
so it is not in the runs.

Runs are seeded from the day, the company and the moment, so asking again at the same moment gives the same runs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

from marketlab.factors import derive_seed
from marketlab.sim.processes import FairValue
from marketlab.sim.rng import SimRng
from marketlab.sim.runner import SimConfig
from marketlab.world import MARKET_SD, MICROS, OWN_VOLATILITY, SECTOR_SD, World

JUMP_RATE = cast(float, SimConfig.__dataclass_fields__["jump_rate"].default)  # jumps per second, as in the simulator
JUMP_SD = cast(float, SimConfig.__dataclass_fields__["jump_sd"].default)


@dataclass(frozen=True, slots=True)
class PathFan:
    symbol: str
    start: int  # paise: the last traded price (or yesterday's close before anything has traded)
    times: list[int]  # microseconds into the day, from now to the close
    paths: list[list[int]]  # paise, one list per run, one price per time
    volatility: float  # per square root of a simulated second
    jump_rate: float
    jump_sd: float


def total_volatility(beta: float) -> float:
    """The company's whole volatility per square root of a second: market, sector and own moves are independent."""
    return math.sqrt((beta * MARKET_SD) ** 2 + SECTOR_SD**2 + OWN_VOLATILITY**2)


def price_paths(world: World, symbol: str, *, runs: int = 200, steps: int = 40) -> PathFan:
    """`runs` possible paths for `symbol` from now to the close, each `steps` steps long."""
    company = next((c for c in world.companies if c.symbol == symbol), None)
    if company is None:
        raise KeyError(symbol)
    if runs < 1 or steps < 1:
        raise ValueError("runs and steps must be at least 1")
    start = world.prices()[symbol]
    t0 = min(max(world.now, world.open_at), world.close_at)
    t1 = world.close_at
    times = [t0 + round(k * (t1 - t0) / steps) for k in range(steps + 1)]
    dt = (t1 - t0) / MICROS / steps
    volatility = total_volatility(company.beta)
    rng = SimRng(derive_seed(world.config.seed, f"paths:{symbol}:{t0}"))
    paths: list[list[int]] = []
    for _ in range(runs):
        fair = FairValue(float(start), volatility, JUMP_RATE, JUMP_SD)
        paths.append([start] + [max(1, round(fair.advance(dt, rng))) for _ in range(steps)])
    return PathFan(symbol, start, times, paths, volatility, JUMP_RATE, JUMP_SD)
