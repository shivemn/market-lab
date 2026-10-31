"""The hidden "fair value" of the stock.

Real prices move because of news and because traders disagree. Here a single hidden number drifts randomly and
occasionally jumps, and the traders react to it with their own errors. This is geometric Brownian motion with
Merton-style jumps:

    log-return over dt seconds = (drift - volatility^2 / 2) * dt + volatility * sqrt(dt) * Z      (Z ~ Normal(0, 1))
                                 plus, with probability 1 - exp(-jump_rate * dt), a jump ~ Normal(0, jump_sd)

The fair value is a float; only traders see it (with noise). The exchange only ever sees integer prices.
"""

from __future__ import annotations

import math

from marketlab.sim.rng import SimRng


class FairValue:
    def __init__(
        self,
        start: float,
        volatility: float,
        jump_rate: float,
        jump_sd: float,
        drift: float = 0.0,
    ) -> None:
        if start <= 0:
            raise ValueError("start must be positive")
        if volatility < 0 or jump_rate < 0 or jump_sd < 0:
            raise ValueError("volatility, jump_rate and jump_sd must not be negative")
        self.value = start
        self.volatility = volatility
        self.jump_rate = jump_rate
        self.jump_sd = jump_sd
        self.drift = drift

    def advance(self, dt_seconds: float, rng: SimRng) -> float:
        """Move forward by dt_seconds and return the new value."""
        if dt_seconds <= 0:
            return self.value
        log_return = (self.drift - 0.5 * self.volatility**2) * dt_seconds
        log_return += self.volatility * math.sqrt(dt_seconds) * rng.gauss()
        if self.jump_rate > 0 and rng.chance(1.0 - math.exp(-self.jump_rate * dt_seconds)):
            log_return += rng.gauss(0.0, self.jump_sd)
        self.value *= math.exp(log_return)
        return self.value
