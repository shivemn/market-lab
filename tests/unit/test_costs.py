"""Charges on delivery trades, with the numbers worked out by hand.

Worked example, a trade of 100 shares at 2,500.00 rupees, so a value of 2,50,000 rupees = 25,000,000 paise,
on a day after 1 March 2026, with no brokerage:

  STT 0.1%                        = 250.00 rupees           = 25,000 paise (buy and sell)
  exchange Rs 307 per crore       = 250000 * 307 / 1e7 = 7.675, rounded up to 7.68 = 768 paise
  SEBI Rs 10 per crore            = 0.25 rupees             = 25 paise
  stamp duty 0.015% (buy only)    = 37.50 rupees            = 3,750 paise
  GST 18% of (7.68 + 0.25)        = 1.4274, rounded 1.43    = 143 paise

  buying:  25,000 + 768 + 25 + 3,750 + 143 = 29,686 paise = Rs 296.86
  selling: 25,000 + 768 + 25 + 143          = 25,936 paise = Rs 259.36
"""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from marketlab.core import Side
from marketlab.costs import PLANS, SCHEDULES, CostBreakdown, CostModel, Rate, per_crore, schedule_on

DAY = date(2026, 11, 1)
VALUE = 25_000_000


def model(plan: str = "zero", day: date = DAY) -> CostModel:
    return CostModel(schedule_on(day), PLANS[plan])


def test_rounding_is_to_the_nearest_paisa_with_halves_up() -> None:
    assert Rate(1, 2).of(1) == 1  # 0.5 -> 1
    assert Rate(1, 2).of(3) == 2  # 1.5 -> 2
    assert Rate(1, 3).of(1) == 0  # 0.33 -> 0
    assert Rate(2, 3).of(1) == 1  # 0.67 -> 1
    assert per_crore(307).of(VALUE) == 768  # 767.5 -> 768
    assert Rate(1, 1000).percent() == "0.1%"


def test_a_buy_of_two_and_a_half_lakh_rupees_with_no_brokerage() -> None:
    cost = model().for_order(Side.BUY, VALUE)
    assert cost == CostBreakdown(stt=25_000, exchange=768, sebi=25, stamp=3_750, gst=143)
    assert cost.total == 29_686


def test_a_sell_pays_no_stamp_duty() -> None:
    cost = model().for_order(Side.SELL, VALUE)
    assert cost == CostBreakdown(stt=25_000, exchange=768, sebi=25, gst=143)
    assert cost.total == 25_936


def test_a_round_trip_must_gain_about_a_fifth_of_a_percent_to_break_even() -> None:
    total = model().for_order(Side.BUY, VALUE).total + model().for_order(Side.SELL, VALUE).total
    assert total == 55_622  # Rs 556.22 on Rs 2,50,000
    assert round(total * 100 / VALUE, 2) == 0.22


def test_a_flat_plan_adds_brokerage_and_demat_and_gst_on_them() -> None:
    # Rs 20 brokerage = 2,000 paise. GST = 18% of (2,000 + 768 + 25) = 18% of 2,793 = 502.74 -> 503
    buy = model("flat20").for_order(Side.BUY, VALUE)
    assert (buy.brokerage, buy.demat, buy.gst) == (2_000, 0, 503)
    assert buy.total == 25_000 + 768 + 25 + 3_750 + 2_000 + 503
    # selling adds the demat fee of Rs 20 too: GST = 18% of (2,000 + 2,000 + 768 + 25) = 18% of 4,793 = 862.74 -> 863
    sell = model("flat20").for_order(Side.SELL, VALUE)
    assert (sell.brokerage, sell.demat, sell.gst) == (2_000, 2_000, 863)


def test_no_fills_means_no_costs() -> None:
    assert model("flat20").for_order(Side.BUY, 0) == CostBreakdown()


def test_the_exchange_charge_changed_on_1_march_2026() -> None:
    before = model(day=date(2026, 2, 28)).for_order(Side.BUY, VALUE)
    after = model(day=date(2026, 3, 1)).for_order(Side.BUY, VALUE)
    assert before.exchange == 743  # 297 per crore: 742.5 -> 743
    assert after.exchange == 768
    assert before.stt == after.stt


def test_a_day_before_the_first_recorded_schedule_is_refused() -> None:
    with pytest.raises(ValueError, match="no charge schedule"):
        schedule_on(date(2020, 1, 1))


def test_every_schedule_says_where_its_numbers_came_from() -> None:
    assert all(s.source for s in SCHEDULES)
    assert [s.effective_from for s in SCHEDULES] == sorted(s.effective_from for s in SCHEDULES)


@given(
    side=st.sampled_from([Side.BUY, Side.SELL]),
    plan=st.sampled_from(sorted(PLANS)),
    fills=st.lists(st.integers(min_value=1, max_value=50_000_000), min_size=1, max_size=8),
)
def test_charging_fill_by_fill_always_adds_up_to_charging_the_whole_order(
    side: Side, plan: str, fills: list[int]
) -> None:
    m = model(plan)
    done = 0
    running = CostBreakdown()
    for fill in fills:
        step = m.for_new_fill(side, done, fill)
        assert all(amount >= 0 for _, amount in step.lines())  # a fill never gives money back
        running = CostBreakdown(*(a + b for (_, a), (_, b) in zip(running.lines(), step.lines(), strict=True)))
        done += fill
    assert running == m.for_order(side, done)


@given(value=st.integers(min_value=1, max_value=10**11))
def test_a_bigger_trade_never_costs_less(value: int) -> None:
    m = model("flat20")
    for side in (Side.BUY, Side.SELL):
        assert m.for_order(side, value + 1).total >= m.for_order(side, value).total
