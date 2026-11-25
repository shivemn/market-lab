"""The price paths behind the Galton board: seeded, starting from the last trade, and true to the simulator's maths."""

from __future__ import annotations

import math
import statistics

import pytest

from marketlab.paths import JUMP_RATE, JUMP_SD, price_paths, total_volatility
from marketlab.world import MICROS, SECTOR_BETA, World, WorldConfig

CONFIG = WorldConfig(seed=11, pre_open_seconds=5, open_seconds=600)


def test_the_same_moment_gives_the_same_paths() -> None:
    a, b = World(CONFIG), World(CONFIG)
    a.advance_to(60 * MICROS)
    b.advance_to(60 * MICROS)
    assert price_paths(a, "UDHAAR").paths == price_paths(b, "UDHAAR").paths


def test_paths_start_from_the_last_trade_not_the_hidden_fair_value() -> None:
    world = World(CONFIG)
    world.advance_to(120 * MICROS)
    fan = price_paths(world, "BUGFIX", runs=20)
    assert fan.start == world.prices()["BUGFIX"]
    assert all(path[0] == fan.start for path in fan.paths)
    assert fan.times[0] == world.now and fan.times[-1] == world.close_at
    assert all(len(path) == len(fan.times) for path in fan.paths)


def test_before_the_open_the_runs_cover_the_whole_session() -> None:
    world = World(CONFIG)
    fan = price_paths(world, "KIRANA", runs=10, steps=10)
    assert fan.times[0] == world.open_at


def test_after_the_close_every_path_is_flat() -> None:
    world = World(WorldConfig(seed=2, pre_open_seconds=5, open_seconds=20))
    world.advance_to(world.close_at)
    fan = price_paths(world, "MACHLI", runs=5, steps=5)
    assert all(set(path) == {fan.start} for path in fan.paths)


def test_an_unknown_company_is_refused() -> None:
    with pytest.raises(KeyError):
        price_paths(World(CONFIG), "NOPE")


def test_end_prices_match_the_formula_for_the_log_return() -> None:
    """log(S_T / S_0) has mean -sigma^2 T / 2 and variance sigma^2 T + lambda T jump_sd^2 (jumps have mean zero)."""
    world = World(CONFIG)
    fan = price_paths(world, "PAKKA", runs=4000, steps=20)
    seconds = (fan.times[-1] - fan.times[0]) / MICROS
    sigma = total_volatility(SECTOR_BETA["secondary"])
    assert fan.volatility == pytest.approx(sigma)
    logs = [math.log(p[-1] / p[0]) for p in fan.paths if p[0] > 0]
    variance = sigma**2 * seconds + JUMP_RATE * seconds * JUMP_SD**2
    mean = statistics.fmean(logs)
    # rounding to whole paise adds a little noise; allow four standard errors
    assert mean == pytest.approx(-0.5 * sigma**2 * seconds, abs=4 * math.sqrt(variance / len(logs)) + 1e-5)
    assert statistics.pvariance(logs) == pytest.approx(variance, rel=0.12)
