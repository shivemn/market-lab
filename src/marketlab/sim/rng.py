"""The one source of randomness for a simulation.

Every random choice in a run, by every trader and by the price process, comes from a single `SimRng` created from
the run's seed. Nothing reads the clock or the operating system's entropy. The same seed therefore gives the
same run.

Python's Mersenne Twister gives identical numbers for identical seeds on every platform. A few functions used on
top of it (log, exp, cos in the normal and log-normal samplers) come from the C maths library, and in rare cases
different machines can differ in the very last bit of a float. So "same seed, same machine and Python" is
guaranteed; "same seed on any machine" holds in practice but is tested only for runs on one machine.
"""

from __future__ import annotations

import random


class SimRng:
    def __init__(self, seed: int) -> None:
        self.seed = seed
        self._random = random.Random(seed)

    def random(self) -> float:
        """A number in [0, 1)."""
        return self._random.random()

    def randint(self, low: int, high: int) -> int:
        """A whole number from low to high, both included."""
        return self._random.randint(low, high)

    def gauss(self, mean: float = 0.0, sd: float = 1.0) -> float:
        return self._random.gauss(mean, sd)

    def exponential(self, rate: float) -> float:
        """Waiting time until the next event of a Poisson process with this rate (events per unit time)."""
        return self._random.expovariate(rate)

    def lognormal(self, mu: float, sigma: float) -> float:
        return self._random.lognormvariate(mu, sigma)

    def chance(self, probability: float) -> bool:
        return self._random.random() < probability
