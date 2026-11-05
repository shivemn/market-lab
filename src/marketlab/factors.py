"""Shared moves: why stocks tend to rise and fall together.

If every company's price were its own independent random walk, an index of twelve of them would hardly move: the
ups and downs would cancel. Real markets are not like that. A big part of most stocks' daily move is shared:
the whole market (news about the economy, interest rates), and the stock's own sector (a bad monsoon hits
agriculture, not software). Only what is left over belongs to the company alone.

The log-return of company i between two moments is built from three parts:

    beta_i  x  (market move)   +   sector_gain_i  x  (move of i's sector)   +   its own random move

The market and sector moves are random walks that are drawn once, from the day's seed, on a one-second grid. So a
whole world of twelve stocks is still fully determined by one seed, and replaying it gives the same day.
"""

from __future__ import annotations

import hashlib

from marketlab.sim.rng import SimRng


def derive_seed(seed: int, label: str) -> int:
    """A new seed for one part of a day (a company, a sector). A hash, so it is the same on every machine."""
    digest = hashlib.sha256(f"{seed}:{label}".encode()).digest()
    return int.from_bytes(digest[:4], "big")


class FactorPath:
    """A random walk fixed in advance on a grid of one second, read at any microsecond by straight-line steps."""

    def __init__(self, seed: int, sd_per_second: float, seconds: int) -> None:
        if seconds <= 0:
            raise ValueError("a factor needs at least one second")
        rng = SimRng(seed)
        self._levels = [0.0]
        for _ in range(seconds):
            self._levels.append(self._levels[-1] + sd_per_second * rng.gauss())
        self._seconds = seconds

    def level(self, microseconds: int) -> float:
        position = max(0.0, microseconds / 1_000_000)
        if position >= self._seconds:
            return self._levels[-1]
        whole = int(position)
        fraction = position - whole
        return self._levels[whole] + fraction * (self._levels[whole + 1] - self._levels[whole])

    def change(self, start: int, end: int) -> float:
        return self.level(end) - self.level(start)
