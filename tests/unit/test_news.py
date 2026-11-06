"""The made-up news: the schedule is fixed by the seed, nothing leaks early, and the move adds up."""

from __future__ import annotations

import pytest

from marketlab.news import QUICK_SECONDS, SLOW_SECONDS, NewsItem, affects, news_change, ramp, schedule
from marketlab.world import CATALOGUE, PracticeWorld, World, WorldConfig

COMPANIES = [(c.symbol, c.name, c.sector) for c in CATALOGUE]
OPEN, CLOSE = 60_000_000, 660_000_000


def test_the_same_seed_gives_the_same_news_and_another_seed_gives_other_news() -> None:
    assert schedule(7, COMPANIES, OPEN, CLOSE) == schedule(7, COMPANIES, OPEN, CLOSE)
    assert schedule(7, COMPANIES, OPEN, CLOSE) != schedule(8, COMPANIES, OPEN, CLOSE)


@pytest.mark.parametrize("seed", range(20))
def test_a_schedule_has_five_items_in_order_inside_the_session_with_a_quiet_end(seed: int) -> None:
    items = schedule(seed, COMPANIES, OPEN, CLOSE)
    assert len(items) == 5 and [i.id for i in items] == list(range(5))
    times = [i.at for i in items]
    assert times == sorted(times)
    assert all(OPEN < t < CLOSE - 100_000_000 for t in times)  # the last item still has time to play out
    assert {i.scope for i in items} <= {"market", "sector", "company"}
    assert all(i.impact_bp != 0 for i in items)


def test_the_reaction_is_fast_first_then_slow_and_adds_up_to_the_whole_move() -> None:
    assert ramp(-1) == 0 and ramp(0) == 0
    assert ramp(QUICK_SECONDS) == pytest.approx(0.6)
    assert ramp(QUICK_SECONDS + SLOW_SECONDS) == pytest.approx(1.0) and ramp(10_000) == 1.0
    item = NewsItem(0, 100_000_000, "company", "UDHAAR", "x", 300, "good")
    whole = news_change([(item, 1.0)], 0, 400_000_000)
    assert whole == pytest.approx(0.03)  # 300 basis points
    parts = news_change([(item, 1.0)], 0, 200_000_000) + news_change([(item, 1.0)], 200_000_000, 400_000_000)
    assert parts == pytest.approx(whole)
    assert news_change([(item, 1.0)], 0, 100_000_000) == 0  # nothing before it comes out


def test_who_a_piece_of_news_touches() -> None:
    market = NewsItem(0, 0, "market", "", "x", 50, "good")
    sector = NewsItem(1, 0, "sector", "primary", "x", 50, "good")
    company = NewsItem(2, 0, "company", "BIJLI", "x", 50, "good")
    assert affects(market, "UDHAAR", "tertiary")
    assert affects(sector, "BHINDI", "primary") and not affects(sector, "UDHAAR", "tertiary")
    assert affects(company, "BIJLI", "secondary") and not affects(company, "JUGAAD", "secondary")


def test_news_really_moves_a_companys_price() -> None:
    """Add a big piece of good news and a bad one for two companies: the first ends the day well above the second."""
    config = WorldConfig(seed=3, pre_open_seconds=5, open_seconds=200)

    def final(news_bp: int) -> int:
        world = World(config)
        world.news = [NewsItem(0, world.open_at + 10_000_000, "company", "UDHAAR", "x", news_bp, "good")]
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


def test_nothing_is_shown_before_its_time_and_sizes_wait_for_the_close() -> None:
    from marketlab.ledger import Ledger

    pw = PracticeWorld(WorldConfig(seed=9, pre_open_seconds=5, open_seconds=600), Ledger(), "you")
    assert pw.news_view() == []
    pw.advance(1000, pause_on_fill=False)
    seen = pw.news_view()
    assert len(seen) == 5 and all(int(str(i["at"])) <= pw.world.now for i in seen)
    assert all(i["impact_bp"] is not None for i in pw.news_view())  # finished: everything is revealed

    early = PracticeWorld(WorldConfig(seed=9, pre_open_seconds=5, open_seconds=600), Ledger(), "you")
    last = early.world.news[-1].at
    early.advance(last / 1_000_000 - 1, pause_on_fill=False)
    shown = early.news_view()
    assert len(shown) == 4  # the last one has not come out yet
    assert all(i["impact_bp"] is None for i in shown)  # sizes stay hidden while the day runs
