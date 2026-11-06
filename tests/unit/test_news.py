"""The made-up news: the schedule is fixed by the seed, nothing leaks early, and the move adds up."""

from __future__ import annotations

import pytest

from marketlab.news import (
    BOX,
    HEADLINES,
    HIT,
    QUICK_SECONDS,
    SILENT,
    SLOW_SECONDS,
    NewsItem,
    affects,
    news_change,
    ramp,
    schedule,
)
from marketlab.world import CATALOGUE, PracticeWorld, World, WorldConfig

COMPANIES = [(c.symbol, c.name, c.sector) for c in CATALOGUE]
OPEN, CLOSE = 60_000_000, 660_000_000


def test_the_same_seed_gives_the_same_news_and_another_seed_gives_other_news() -> None:
    assert schedule(7, COMPANIES, OPEN, CLOSE) == schedule(7, COMPANIES, OPEN, CLOSE)
    assert schedule(7, COMPANIES, OPEN, CLOSE) != schedule(8, COMPANIES, OPEN, CLOSE)


@pytest.mark.parametrize("seed", range(20))
def test_a_schedule_has_eight_events_in_order_inside_the_session_with_a_quiet_end(seed: int) -> None:
    items = schedule(seed, COMPANIES, OPEN, CLOSE)
    assert len(items) == HEADLINES + SILENT and [i.id for i in items] == list(range(8))
    times = [i.at for i in items]
    assert times == sorted(times)
    assert all(OPEN < t < CLOSE - 100_000_000 for t in times)  # the last item still has time to play out
    assert {i.scope for i in items} <= {"market", "sector", "company"}
    assert sum(i.kind == "silent" for i in items) == SILENT
    assert all(i.headline == "" for i in items if i.kind == "silent")
    assert all(i.headline != "" for i in items if i.kind != "silent")
    headlines = [i.headline for i in items if i.kind != "silent"]
    assert len(set(headlines)) == len(headlines)  # no repeats in a day
    assert all(i.impact_bp != 0 for i in items if i.kind == "silent")


def test_the_reaction_is_fast_first_then_slow_and_adds_up_to_the_whole_move() -> None:
    assert ramp(-1) == 0 and ramp(0) == 0
    assert ramp(QUICK_SECONDS) == pytest.approx(0.6)
    assert ramp(QUICK_SECONDS + SLOW_SECONDS) == pytest.approx(1.0) and ramp(10_000) == 1.0
    item = NewsItem(0, 100_000_000, "company", "UDHAAR", "x", 300, "major")
    whole = news_change([(item, 1.0)], 0, 400_000_000)
    assert whole == pytest.approx(0.03)  # 300 basis points
    parts = news_change([(item, 1.0)], 0, 200_000_000) + news_change([(item, 1.0)], 200_000_000, 400_000_000)
    assert parts == pytest.approx(whole)
    assert news_change([(item, 1.0)], 0, 100_000_000) == 0  # nothing before it comes out


def test_who_a_piece_of_news_touches() -> None:
    market = NewsItem(0, 0, "market", "", "x", 50, "major")
    sector = NewsItem(1, 0, "sector", "primary", "x", 50, "major")
    company = NewsItem(2, 0, "company", "BIJLI", "x", 50, "major")
    assert affects(market, "UDHAAR", "tertiary")
    assert affects(sector, "BHINDI", "primary") and not affects(sector, "UDHAAR", "tertiary")
    assert affects(company, "BIJLI", "secondary") and not affects(company, "JUGAAD", "secondary")


def test_news_really_moves_a_companys_price() -> None:
    """Add a big piece of good news and a bad one for two companies: the first ends the day well above the second."""
    config = WorldConfig(seed=3, pre_open_seconds=5, open_seconds=200)

    def final(news_bp: int) -> int:
        world = World(config)
        world.news = [NewsItem(0, world.open_at + 10_000_000, "company", "UDHAAR", "x", news_bp, "major")]
        world.sims = {s: s2 for s, s2 in world.sims.items()}
        # rebuild only UDHAAR with the news in place
        from marketlab.sim import Simulation
        from marketlab.world import STALE_FRACTION

        company = next(c for c in world.companies if c.symbol == "UDHAAR")
        world.sims["UDHAAR"] = Simulation(world.sim_config(company), world._common(company), STALE_FRACTION)
        world.advance_to(world.close_at)
        return world.prices()["UDHAAR"]

    good, none, bad = final(800), final(1), final(-800)
    assert good > none > bad
    assert (good - bad) / none > 0.08  # 800 bp each way, minus the noise


def test_major_headlines_usually_move_prices_and_minor_ones_rarely_do() -> None:
    """The dice behave as designed: about 75% of major headlines and 15% of minor ones move the price."""
    hits = {"major": [0, 0], "minor": [0, 0]}
    for seed in range(1500):
        for item in schedule(seed, COMPANIES, OPEN, CLOSE):
            if item.kind in hits:
                hits[item.kind][0] += item.impact_bp != 0
                hits[item.kind][1] += 1
    for kind in ("major", "minor"):
        moved, total = hits[kind]
        assert abs(moved / total - HIT[kind]) < 0.03, (kind, moved / total)


def test_a_major_headline_with_an_obvious_direction_usually_goes_that_way_but_not_always() -> None:
    leans = {text: lean for scope, kind, lean, text in BOX if kind == "major" and lean != 0 and scope == "market"}
    with_lean = against = 0
    for seed in range(3000):
        for item in schedule(seed, COMPANIES, OPEN, CLOSE):
            lean = leans.get(item.headline)
            if lean is not None and item.impact_bp != 0:
                if (item.impact_bp > 0) == (lean > 0):
                    with_lean += 1
                else:
                    against += 1
    share = with_lean / (with_lean + against)
    assert 0.75 < share < 0.85 and against > 0  # about four in five, and the exceptions really happen


def test_a_minor_headline_that_does_move_the_price_has_no_favourite_direction() -> None:
    up = down = 0
    for seed in range(4000):
        for item in schedule(seed, COMPANIES, OPEN, CLOSE):
            if item.kind == "minor" and item.impact_bp != 0:
                up += item.impact_bp > 0
                down += item.impact_bp < 0
    assert abs(up / (up + down) - 0.5) < 0.05


def test_nothing_is_shown_before_its_time_and_silent_shocks_and_sizes_wait_for_the_close() -> None:
    from marketlab.ledger import Ledger

    config = WorldConfig(seed=9, pre_open_seconds=5, open_seconds=600)
    pw = PracticeWorld(config, Ledger(), "you")
    assert pw.news_view() == []
    pw.advance(1000, pause_on_fill=False)
    seen = pw.news_view()
    assert len(seen) == HEADLINES + SILENT  # at the close the silent shocks are revealed too
    assert all(int(str(i["at"])) <= pw.world.now for i in seen)
    assert all(i["impact_bp"] is not None for i in seen)
    assert sum(bool(i["silent"]) for i in seen) == SILENT

    early = PracticeWorld(config, Ledger(), "you")
    last = early.world.news[-1].at
    early.advance(last / 1_000_000 - 1, pause_on_fill=False)
    shown = early.news_view()
    assert all(not i["silent"] and i["headline"] for i in shown)  # silent shocks are not announced
    assert all(i["impact_bp"] is None for i in shown)  # sizes stay hidden while the day runs
    assert len(shown) <= HEADLINES


def test_a_session_too_short_for_news_has_none() -> None:
    assert schedule(1, COMPANIES, OPEN, OPEN + 120_000_000) == []
