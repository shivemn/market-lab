from __future__ import annotations

from marketlab.ledger import Ledger
from marketlab.rules import benchmarks
from marketlab.world import PracticeWorld, WorldConfig


def by_key(paths: dict[str, list[int]]) -> dict[str, int]:
    return {b.key: b.basis_points for b in benchmarks(paths)}


def test_holding_equally_averages_each_companys_move() -> None:
    result = by_key({"A": [100, 110], "B": [100, 90]})  # +10% and -10%
    assert result["hold"] == 0 and result["cash"] == 0


def test_the_trend_rule_stays_in_cash_until_it_has_enough_looks_and_follows_a_rise() -> None:
    rising = {"A": [100, 101, 102, 103, 110, 120]}
    result = by_key(rising)
    # looks 0..2 are cash; from look 3 the price (103) is above the average of 100,101,102 so it holds 103->110->120
    assert result["trend"] == round((120 / 103 - 1) * 10_000)
    assert result["hold"] == round((120 / 100 - 1) * 10_000)


def test_the_trend_rule_sits_out_a_falling_market() -> None:
    falling = {"A": [100, 98, 96, 94, 90, 80]}
    assert by_key(falling)["trend"] == 0  # never above its average, so never held


def test_a_finished_day_has_three_comparisons_and_an_unfinished_one_has_none() -> None:
    pw = PracticeWorld(WorldConfig(seed=4, pre_open_seconds=5, open_seconds=600), Ledger(), "you")
    assert pw.benchmarks_view() == []
    pw.advance(10_000, pause_on_fill=False)
    view = pw.benchmarks_view()
    assert [b["key"] for b in view] == ["cash", "hold", "trend"]
    paths = pw.price_paths()
    assert all(len(p) == 11 for p in paths.values())  # the open plus ten minutes
