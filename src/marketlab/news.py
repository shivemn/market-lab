"""News: a few made-up announcements in each day that move prices.

Each day has a short schedule of news items, drawn from the day's seed so the same day always has the same news. An item
has a time, a target (the whole market, one sector or one company), a headline and a size. When it comes out, the
target's price takes most of its move quickly and the rest more slowly, the way real prices react: first the shock,
then people catching up.

The news enters the price the same way the shared market and sector moves do (see `factors.py`): as an extra
log-return added to each affected company's fair value. So nothing else about the exchange changes, and a replay from
the seed still gives the same day exactly.

What the person may see is limited on purpose. Before an item's time it is invisible. After it, the headline shows,
with a tone (good, bad or unclear). How far it moved the price is only revealed once the day ends, so the news is
something to judge and not a cheat sheet.
"""

from __future__ import annotations

from dataclasses import dataclass

from marketlab.factors import derive_seed
from marketlab.sim.rng import SimRng

MICROS = 1_000_000
QUICK_SECONDS = 5  # the first, fast part of the reaction
QUICK_SHARE = 0.6  # how much of the total move happens in that first part
SLOW_SECONDS = 120  # the rest drifts in over this long


@dataclass(frozen=True, slots=True)
class NewsItem:
    id: int
    at: int  # microseconds into the day
    scope: str  # "market", "sector" or "company"
    target: str  # "" for the market, a sector key, or a company symbol
    headline: str
    impact_bp: int  # the full move in basis points of price (signed), reached over about two minutes
    tone: str  # "good", "bad" or "unclear": what the headline lets you tell about the direction


def ramp(since: float) -> float:
    """How much of an item's total move has happened `since` seconds after it came out (0 to 1)."""
    if since <= 0:
        return 0.0
    if since <= QUICK_SECONDS:
        return QUICK_SHARE * since / QUICK_SECONDS
    if since <= QUICK_SECONDS + SLOW_SECONDS:
        return QUICK_SHARE + (1 - QUICK_SHARE) * (since - QUICK_SECONDS) / SLOW_SECONDS
    return 1.0


def news_change(items: list[tuple[NewsItem, float]], start: int, end: int) -> float:
    """The log-return news adds to one company between two moments. Each item comes with the company's weight on it."""
    total = 0.0
    for item, weight in items:
        moved = ramp((end - item.at) / MICROS) - ramp((start - item.at) / MICROS)
        total += weight * (item.impact_bp / 10_000) * moved
    return total


# Headlines. {name} is the company or sector; the first line of each pair is for a rise and the second for a fall.
_COMPANY_CLEAR = (
    ("{name} wins a large order from the government", "{name} loses its biggest customer"),
    ("{name} reports profits well above what was expected", "{name} reports a surprise loss for the quarter"),
    ("{name} announces a record dividend", "{name} is raided by tax officials"),
    ("{name} signs a deal to supply a foreign buyer", "{name} halts its main factory after an accident"),
)
_COMPANY_UNCLEAR = (
    "{name} announces a change at the top",
    "{name} says it will restructure its business",
    "{name} calls a surprise meeting with investors",
    "{name} confirms talks about a merger",
)
_SECTOR_CLEAR = (
    ("A good monsoon lifts hopes for {name}", "A weak monsoon worries {name}"),
    ("The government announces support for {name}", "New rules make life harder for {name}"),
    ("Export orders for {name} jump", "Export orders for {name} fall sharply"),
)
_MARKET_CLEAR = (
    ("The central bank cuts interest rates", "The central bank raises interest rates"),
    ("Foreign investors buy heavily in India", "Foreign investors pull money out of India"),
    ("Growth figures beat forecasts", "Growth figures miss forecasts"),
)

_SECTOR_NAMES = {
    "primary": "farm, fishing and mining companies",
    "secondary": "factories and power companies",
    "tertiary": "banks, retailers and service companies",
    "quaternary": "technology and research companies",
}


def schedule(
    seed: int,
    companies: list[tuple[str, str, str]],  # (symbol, name, sector key)
    open_at: int,
    close_at: int,
) -> list[NewsItem]:
    """About five items, spread over the trading session, always the same for the same seed."""
    rng = SimRng(derive_seed(seed, "news"))
    span = close_at - open_at
    count = 5
    # one slot per item so two never land together; the last two minutes stay quiet so a move can finish
    usable = span - 2 * 60 * MICROS
    slot = usable // count
    kinds = ["market", "sector", "sector", "company", "company"]
    # shuffle with the day's own random numbers
    for i in range(len(kinds) - 1, 0, -1):
        j = rng.randint(0, i)
        kinds[i], kinds[j] = kinds[j], kinds[i]
    items: list[NewsItem] = []
    for index, scope in enumerate(kinds):
        at = open_at + 30 * MICROS + index * slot + rng.randint(0, max(1, slot - 40 * MICROS))
        up = rng.chance(0.5)
        unclear = scope == "company" and rng.chance(0.4)
        if scope == "company":
            symbol, name, _ = companies[rng.randint(0, len(companies) - 1)]
            target = symbol
            size = 150 + rng.randint(0, 250)
            if unclear:
                headline = _COMPANY_UNCLEAR[rng.randint(0, len(_COMPANY_UNCLEAR) - 1)].format(name=name)
            else:
                pair = _COMPANY_CLEAR[rng.randint(0, len(_COMPANY_CLEAR) - 1)]
                headline = pair[0 if up else 1].format(name=name)
        elif scope == "sector":
            keys = sorted({sector for _, _, sector in companies})
            target = keys[rng.randint(0, len(keys) - 1)]
            size = 80 + rng.randint(0, 120)
            pair = _SECTOR_CLEAR[rng.randint(0, len(_SECTOR_CLEAR) - 1)]
            headline = pair[0 if up else 1].format(name=_SECTOR_NAMES.get(target, target))
        else:
            target = ""
            size = 50 + rng.randint(0, 70)
            pair = _MARKET_CLEAR[rng.randint(0, len(_MARKET_CLEAR) - 1)]
            headline = pair[0 if up else 1]
        tone = "unclear" if unclear else ("good" if up else "bad")
        items.append(NewsItem(index, at, scope, target, headline, size if up else -size, tone))
    items.sort(key=lambda item: item.at)
    return [NewsItem(i, n.at, n.scope, n.target, n.headline, n.impact_bp, n.tone) for i, n in enumerate(items)]


def affects(item: NewsItem, symbol: str, sector: str) -> bool:
    return (
        item.scope == "market"
        or (item.scope == "sector" and item.target == sector)
        or (item.scope == "company" and item.target == symbol)
    )
