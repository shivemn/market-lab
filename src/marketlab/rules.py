"""Simple rules to compare yourself with: what a day would have paid if nobody had to think.

These are shadow portfolios worked out from the day's prices after the day has ended. They do not trade in the market,
so they never move a price, and they ignore taxes and charges. The point is to give your result something to be set
against: "I made 0.4%" means more when holding every company equally made 0.1%, or when a trend rule lost 0.3%.

Prices are looked at once a simulated minute, which is how often a person following the market might look.
"""

from __future__ import annotations

from dataclasses import dataclass

LOOKBACK = 3  # the trend rule compares a price with the average of the last three looks


@dataclass(frozen=True, slots=True)
class Benchmark:
    key: str
    label: str
    basis_points: int  # result for the day, in hundredths of a percent
    note: str


def _bp(ratio: float) -> int:
    return round((ratio - 1) * 10_000)


def benchmarks(paths: dict[str, list[int]]) -> list[Benchmark]:
    """`paths` holds each company's price at the open and at the end of every simulated minute after it (paise)."""
    names = sorted(paths)
    steps = min(len(p) for p in paths.values()) - 1
    if steps < 1:
        return []
    # hold all twelve in equal amounts from open to close
    hold = sum(paths[n][steps] / paths[n][0] for n in names) / len(names)
    # trend rule: each minute, hold a company only if its price is above the average of its last few looks
    wealth = 1.0
    for k in range(steps):
        gains = []
        for n in names:
            p = paths[n]
            if k >= LOOKBACK and p[k] > sum(p[k - LOOKBACK : k]) / LOOKBACK:
                gains.append(p[k + 1] / p[k])
            else:
                gains.append(1.0)  # sat in cash this minute
        wealth *= sum(gains) / len(gains)
    return [
        Benchmark("cash", "Stay in cash", 0, "Do nothing. A fixed 0.00% before charges."),
        Benchmark(
            "hold", "Hold all twelve equally", _bp(hold), "Split the money evenly at the open, sell at the close."
        ),
        Benchmark(
            "trend",
            "Follow the trend",
            _bp(wealth),
            f"Each minute, hold a company only if it is above its average of the last {LOOKBACK} minutes.",
        ),
    ]
