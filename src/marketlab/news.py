"""News: a box of made-up headlines, a few drawn each day, and prices that only sometimes react.

Real news comes in three kinds, and this module mimics each:

1. News that usually matters (a war breaks out, interest rates rise). It *usually* moves prices, and usually the way you
   would expect, but sometimes it does nothing and sometimes it goes the other way.
2. News that usually does not matter (a robbery in some locality, a chief executive's interview). It rarely moves
   prices, but now and then it does, in a direction nobody can tell in advance.
3. No news at all. Prices still jump now and then for reasons nobody sees. Here a couple of "silent shocks" do that.

There is no table of which headline moves which stock. Each headline in the box has a *class* (major or minor) and an
optional lean (the obvious direction, if any). Each day draws about six headlines at random, and then rolls dice: does
this one move the price (about 75% of the time for major, 15% for minor), and which way (major: with its lean four times
in five; minor: a coin toss).

The news enters the price the way the shared market and sector moves do (see `factors.py`): as an extra log-return added
to each affected company's fair value. So the exchange is unchanged and a replay from the seed gives the same day. The
dice are rolled when the day is built, from the seed.

What the person may see is limited on purpose. Before an item's time it is invisible, and silent shocks stay invisible
until the day is over. A headline shows with no hint of whether it will matter. What each one did is revealed at the
close, so the news is something to judge and not a cheat sheet.
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
    headline: str  # empty for a silent shock
    impact_bp: int  # the full move in basis points of price (signed; 0 means it did not move the price)
    kind: str  # "major", "minor" or "silent": kept for tests and the end-of-day review, never shown during the day


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


# The box. (scope, class, lean, headline). Lean is +1 or -1 when there is an obvious direction, 0 when there is none.
# {name} is the company, or the sector described in words.
BOX: tuple[tuple[str, str, int, str], ...] = (
    # whole market, major
    ("market", "major", -1, "The central bank raises interest rates"),
    ("market", "major", 1, "The central bank cuts interest rates"),
    ("market", "major", -1, "War breaks out between two big trading partners"),
    ("market", "major", 1, "Foreign investors buy heavily in India"),
    ("market", "major", -1, "Foreign investors pull money out of India"),
    ("market", "major", 0, "Growth figures for the quarter are published"),
    ("market", "major", -1, "Oil prices jump to a two-year high"),
    # whole market, minor
    ("market", "minor", 0, "The finance minister gives a speech at an industry event"),
    ("market", "minor", 0, "A foreign rating agency publishes a routine report on India"),
    ("market", "minor", 0, "Trading volumes were low on the exchange last week"),
    ("market", "minor", 0, "A protest blocks roads in the capital for a day"),
    # sectors, major
    ("sector", "major", 1, "A good monsoon lifts hopes for {name}"),
    ("sector", "major", -1, "A weak monsoon worries {name}"),
    ("sector", "major", 1, "The government announces support for {name}"),
    ("sector", "major", -1, "New rules make life harder for {name}"),
    ("sector", "major", 0, "Export figures for {name} are released"),
    # sectors, minor
    ("sector", "minor", 0, "A trade body holds its annual meeting for {name}"),
    ("sector", "minor", 0, "A survey asks people what they think of {name}"),
    ("sector", "minor", 0, "A minister visits a factory that supplies {name}"),
    # companies, major
    ("company", "major", 1, "{name} wins a large order from the government"),
    ("company", "major", -1, "{name} loses its biggest customer"),
    ("company", "major", 1, "{name} reports profits well above what was expected"),
    ("company", "major", -1, "{name} reports a surprise loss for the quarter"),
    ("company", "major", -1, "Tax officials raid {name}"),
    ("company", "major", 0, "{name} announces a merger"),
    ("company", "major", 0, "{name} announces a change of chief executive"),
    # companies, minor
    ("company", "minor", 0, "A robbery is reported near a {name} warehouse"),
    ("company", "minor", 0, "{name}'s chief executive gives a newspaper interview"),
    ("company", "minor", 0, "{name} changes the design of its logo"),
    ("company", "minor", 0, "{name} sponsors a local cricket tournament"),
    ("company", "minor", 0, "A former employee of {name} writes a critical blog post"),
    ("company", "minor", 0, "{name} opens a new office in another city"),
)

HIT = {"major": 0.75, "minor": 0.15}  # the chance that a headline of each class moves the price at all
FOLLOW_LEAN = 0.8  # when a major headline has an obvious direction, how often the price goes that way
MIN_SESSION_US = 300 * MICROS  # shorter sessions than five minutes get no news
HEADLINES = 6  # drawn from the box each day
SILENT = 2  # moves with no headline at all
SIZE = {"market": (50, 120), "sector": (80, 200), "company": (150, 400)}  # basis points, before a minor's discount
MINOR_DISCOUNT = 0.6

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
    """Eight events spread over the session, always the same for the same seed: six headlines and two silent shocks."""
    if close_at - open_at < MIN_SESSION_US:
        return []  # a very short test day has no room for news
    rng = SimRng(derive_seed(seed, "news"))
    total = HEADLINES + SILENT
    usable = (close_at - open_at) - 2 * 60 * MICROS  # the last two minutes stay quiet so a move can finish
    slot = usable // total
    # draw the headlines from the box without repeats
    pool = list(range(len(BOX)))
    drawn: list[int | None] = []
    for _ in range(HEADLINES):
        drawn.append(pool.pop(rng.randint(0, len(pool) - 1)))
    drawn += [None] * SILENT  # None stands for a silent shock
    for i in range(len(drawn) - 1, 0, -1):  # shuffle, so the silent ones fall anywhere in the day
        j = rng.randint(0, i)
        drawn[i], drawn[j] = drawn[j], drawn[i]
    sectors = sorted({sector for _, _, sector in companies})
    items: list[NewsItem] = []
    for index, choice in enumerate(drawn):
        at = open_at + 30 * MICROS + index * slot + rng.randint(0, max(1, slot - 40 * MICROS))
        if choice is None:
            symbol = companies[rng.randint(0, len(companies) - 1)][0]
            size = 100 + rng.randint(0, 200)
            items.append(NewsItem(index, at, "company", symbol, "", size if rng.chance(0.5) else -size, "silent"))
            continue
        scope, kind, lean, template = BOX[choice]
        if scope == "company":
            symbol, name, _ = companies[rng.randint(0, len(companies) - 1)]
            target, label = symbol, name
        elif scope == "sector":
            target = sectors[rng.randint(0, len(sectors) - 1)]
            label = _SECTOR_NAMES.get(target, target)
        else:
            target, label = "", ""
        low, high = SIZE[scope]
        size = low + rng.randint(0, high - low)
        if kind == "minor":
            size = round(size * MINOR_DISCOUNT)
        moves = rng.chance(HIT[kind])
        up = rng.chance(FOLLOW_LEAN) == (lean > 0) if lean != 0 else rng.chance(0.5)
        impact = (size if up else -size) if moves else 0
        items.append(NewsItem(index, at, scope, target, template.format(name=label), impact, kind))
    items.sort(key=lambda item: item.at)
    return [NewsItem(i, n.at, n.scope, n.target, n.headline, n.impact_bp, n.kind) for i, n in enumerate(items)]


def affects(item: NewsItem, symbol: str, sector: str) -> bool:
    return (
        item.scope == "market"
        or (item.scope == "sector" and item.target == sector)
        or (item.scope == "company" and item.target == symbol)
    )
