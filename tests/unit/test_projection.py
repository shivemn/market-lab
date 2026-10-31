"""Rebuilding the market from events alone, checked against a hand-worked day (see scenario.py)."""

from __future__ import annotations

from marketlab.core import LevelView, Session, Side
from marketlab.projection import MarketState
from tests.helpers import DEMO
from tests.unit.scenario import scripted_day


def state_after(step: str) -> MarketState:
    events, marks = scripted_day()
    state = MarketState(DEMO)
    state.apply_all(events[: marks[step]])
    return state


def test_pre_open_holds_orders_without_trading() -> None:
    state = state_after("cancel2")
    assert state.session is Session.PRE_OPEN
    assert state.trades == 0 and state.last_price is None
    # Order 2 was cancelled; the market buy (order 5) waits for the auction.
    assert set(state.orders) == {1, 3, 4}
    assert state.pending_market == {5: 30}


def test_the_auction_trades_130_shares_at_the_equilibrium_price() -> None:
    state = state_after("open")
    assert state.session is Session.OPEN
    assert state.opening_price == 250_000
    assert state.last_price == 250_000
    assert (state.trades, state.volume) == (3, 130)
    assert state.pending_market == {}
    # Buyers were all filled. Order 4 (120 for sale) sold 50 and has 70 left; order 3 sold all 80.
    assert state.orders.keys() == {4}
    assert state.depth(Side.SELL) == [LevelView(250_000, 70, 1)]
    assert state.depth(Side.BUY) == []


def test_modify_keeps_or_loses_the_place_in_the_queue() -> None:
    before = state_after("o8")
    assert before.queue(Side.BUY, 249_900) == [(6, 40), (7, 60)]
    shrunk = state_after("shrink7")
    assert shrunk.queue(Side.BUY, 249_900) == [(6, 40), (7, 30)]  # 7 is smaller and still behind 6
    moved = state_after("move6")
    assert moved.queue(Side.BUY, 249_900) == [(7, 30)]
    assert moved.queue(Side.BUY, 249_950) == [(8, 20), (6, 40)]  # 6 joined the back of the 249,950 queue


def test_ioc_fills_the_front_of_the_queue_and_the_rest_is_cancelled() -> None:
    state = state_after("ioc9")
    # Order 9 sells 20 at 249,950 and hits order 8 (first in line); nothing is left of 9.
    assert state.queue(Side.BUY, 249_950) == [(6, 40)]
    assert 9 not in state.orders
    assert state.last_price == 249_950


def test_rejections_change_nothing() -> None:
    for before, rejected in (("ioc9", "bad10"), ("mkt11", "cancel99")):
        earlier, later = state_after(before), state_after(rejected)
        assert later.depth(Side.BUY) == earlier.depth(Side.BUY)
        assert later.depth(Side.SELL) == earlier.depth(Side.SELL)
        assert later.last_price == earlier.last_price
        assert later.events_applied == earlier.events_applied + 1  # the rejection itself is the only event


def test_market_orders_trade_at_the_resting_price() -> None:
    sold = state_after("mkt11")
    # The market sell of 25 hit order 6 (40 -> 15) at 249,950.
    assert sold.queue(Side.BUY, 249_950) == [(6, 15)]
    assert sold.last_price == 249_950
    bought = state_after("mkt12")
    # The market buy of 30 took 30 of order 4's 70 at 2,500.00.
    assert bought.queue(Side.SELL, 250_000) == [(4, 40)]
    assert bought.last_price == 250_000


def test_open_high_low_and_totals_at_the_end_of_the_day() -> None:
    state = state_after("close")
    assert state.session is Session.CLOSED
    assert state.orders == {} and state.pending_market == {}
    assert (state.high, state.low) == (250_000, 249_950)
    assert state.trades == 3 + 1 + 1 + 1  # auction 3, order 9, order 11, order 12
    assert state.volume == 130 + 20 + 25 + 30
