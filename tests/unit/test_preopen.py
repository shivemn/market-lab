"""The pre-open session and the opening auction, with hand-calculated numbers.

Reference price 250000 paise, tick 5, band 225000 to 275000.
"""

from __future__ import annotations

import pytest

from marketlab.core import (
    AuctionResult,
    CancelOrder,
    CancelReason,
    Event,
    Exchange,
    LevelView,
    ModifyOrder,
    NewOrder,
    OrderAccepted,
    OrderCancelled,
    OrderExpired,
    OrderModified,
    OrderRejected,
    RejectReason,
    Session,
    SessionChanged,
    Side,
    TimeInForce,
    Trade,
)
from tests.helpers import DEMO, limit, market


def pre_open_exchange() -> Exchange:
    exchange = Exchange(DEMO)
    exchange.set_session(Session.PRE_OPEN, 0)
    return exchange


def trades(events: list[Event]) -> list[tuple[int, int, int, int]]:
    """(price, quantity, buy order id, sell order id) for each trade."""
    return [(e.price, e.quantity, e.buy_order_id, e.sell_order_id) for e in events if isinstance(e, Trade)]


def auction_result(events: list[Event]) -> AuctionResult:
    found = [e for e in events if isinstance(e, AuctionResult)]
    assert len(found) == 1
    return found[0]


def reject_reason(events: list[Event]) -> RejectReason:
    rejected = [e for e in events if isinstance(e, OrderRejected)]
    assert len(rejected) == 1
    return rejected[0].reason


def test_pre_open_collects_orders_and_nothing_trades() -> None:
    ex = pre_open_exchange()
    first = ex.submit(NewOrder(limit(1, Side.BUY, 250_010, 10)), 1)
    second = ex.submit(NewOrder(limit(2, Side.SELL, 250_000, 10)), 2)  # overlaps the buy, but must not trade
    assert [type(e) for e in first] == [OrderAccepted]
    assert [type(e) for e in second] == [OrderAccepted]
    assert len(ex.book) == 2
    assert ex.book.is_crossed()  # allowed before the auction


def test_market_orders_are_accepted_in_pre_open_even_with_nothing_to_trade_against() -> None:
    ex = pre_open_exchange()
    events = ex.submit(NewOrder(market(1, Side.BUY, 10)), 1)
    assert [type(e) for e in events] == [OrderAccepted]
    assert len(ex.book) == 0  # market orders wait in a separate list, never on the book


def test_opening_auction_with_hand_calculated_fills() -> None:
    ex = pre_open_exchange()
    ex.submit(NewOrder(limit(1, Side.BUY, 250_010, 100)), 1)
    ex.submit(NewOrder(limit(2, Side.BUY, 250_000, 50)), 2)
    ex.submit(NewOrder(limit(3, Side.SELL, 250_000, 80)), 3)
    ex.submit(NewOrder(limit(4, Side.SELL, 250_010, 60)), 4)

    events = ex.set_session(Session.OPEN, 10)

    # Equilibrium is 250010 with volume 100. Buyer 1 (100) is filled by the best-priced sellers first:
    # seller 3 (250000) for 80, then seller 4 (250010) for the last 20. Everything trades at 250010.
    assert [type(e) for e in events] == [AuctionResult, Trade, Trade, SessionChanged]
    result = auction_result(events)
    assert (result.price, result.volume, result.opening_price) == (250_010, 100, 250_010)
    assert (result.unmatched_buy, result.unmatched_sell) == (0, 40)
    assert trades(events) == [(250_010, 80, 1, 3), (250_010, 20, 1, 4)]

    # Buyer 2 (priced below the auction price) and the rest of seller 4 move on to continuous trading.
    assert ex.session is Session.OPEN
    assert ex.book.depth(Side.BUY) == [LevelView(250_000, 50, 1)]
    assert ex.book.depth(Side.SELL) == [LevelView(250_010, 40, 1)]
    assert not ex.book.is_crossed()


def test_auction_trades_have_no_aggressor_and_the_sequence_has_no_gaps() -> None:
    ex = Exchange(DEMO)
    seen: list[Event] = list(ex.set_session(Session.PRE_OPEN, 0))
    seen += ex.submit(NewOrder(limit(1, Side.BUY, 250_000, 10)), 1)
    seen += ex.submit(NewOrder(limit(2, Side.SELL, 250_000, 10)), 2)
    seen += ex.set_session(Session.OPEN, 3)
    assert [e.seq for e in seen] == list(range(1, len(seen) + 1))
    assert all(e.aggressor_side is None for e in seen if isinstance(e, Trade))


def test_orders_at_the_same_price_fill_oldest_first_in_the_auction() -> None:
    ex = pre_open_exchange()
    ex.submit(NewOrder(limit(1, Side.BUY, 250_000, 50)), 1)
    ex.submit(NewOrder(limit(2, Side.BUY, 250_000, 50)), 2)
    ex.submit(NewOrder(limit(3, Side.SELL, 250_000, 60)), 3)
    events = ex.set_session(Session.OPEN, 4)
    assert trades(events) == [(250_000, 50, 1, 3), (250_000, 10, 2, 3)]
    assert ex.book.depth(Side.BUY) == [LevelView(250_000, 40, 1)]


def test_market_orders_have_priority_over_limit_orders_in_the_auction() -> None:
    ex = pre_open_exchange()
    ex.submit(NewOrder(limit(1, Side.SELL, 250_000, 50)), 1)
    ex.submit(NewOrder(limit(2, Side.BUY, 250_010, 100)), 2)
    ex.submit(NewOrder(market(3, Side.BUY, 30)), 3)  # arrives last but is served first
    events = ex.set_session(Session.OPEN, 4)
    # Every price from 250000 to 250010 gives volume 50 and the same imbalance, so the price closest to the
    # reference (250000) is chosen. Market buyer 3 takes 30, then limit buyer 2 takes the other 20.
    assert auction_result(events).price == 250_000
    assert trades(events) == [(250_000, 30, 3, 1), (250_000, 20, 2, 1)]
    assert ex.book.depth(Side.BUY) == [LevelView(250_010, 80, 1)]
    assert ex.book.depth(Side.SELL) == []


def test_an_unfilled_market_order_is_cancelled_after_the_auction() -> None:
    ex = pre_open_exchange()
    ex.submit(NewOrder(limit(1, Side.SELL, 250_000, 40)), 1)
    ex.submit(NewOrder(market(2, Side.BUY, 100)), 2)
    events = ex.set_session(Session.OPEN, 3)
    assert trades(events) == [(250_000, 40, 2, 1)]
    cancelled = [e for e in events if isinstance(e, OrderCancelled)]
    assert [(c.order_id, c.quantity, c.reason) for c in cancelled] == [(2, 60, CancelReason.MARKET_REMAINDER)]
    assert len(ex.book) == 0


def test_an_ioc_order_does_not_survive_the_auction() -> None:
    ex = pre_open_exchange()
    ex.submit(NewOrder(limit(1, Side.BUY, 250_000, 100, tif=TimeInForce.IOC)), 1)
    ex.submit(NewOrder(limit(2, Side.SELL, 250_000, 30)), 2)
    events = ex.set_session(Session.OPEN, 3)
    assert trades(events) == [(250_000, 30, 1, 2)]
    cancelled = [e for e in events if isinstance(e, OrderCancelled)]
    assert [(c.order_id, c.quantity, c.reason) for c in cancelled] == [(1, 70, CancelReason.IOC_REMAINDER)]
    assert len(ex.book) == 0


def test_no_overlap_means_no_opening_trade_and_the_reference_price_is_the_opening_price() -> None:
    ex = pre_open_exchange()
    ex.submit(NewOrder(limit(1, Side.BUY, 249_990, 10)), 1)
    ex.submit(NewOrder(limit(2, Side.SELL, 250_010, 10)), 2)
    events = ex.set_session(Session.OPEN, 3)
    result = auction_result(events)
    assert result.price is None and result.volume == 0 and result.opening_price == 250_000
    assert trades(events) == []
    assert ex.book.best_bid() == 249_990 and ex.book.best_ask() == 250_010


def test_an_empty_pre_open_opens_at_the_reference_price() -> None:
    ex = pre_open_exchange()
    events = ex.set_session(Session.OPEN, 5)
    assert [type(e) for e in events] == [AuctionResult, SessionChanged]
    result = auction_result(events)
    assert (result.price, result.volume, result.opening_price) == (None, 0, 250_000)


def test_cancel_works_for_limit_and_market_orders_in_pre_open() -> None:
    ex = pre_open_exchange()
    ex.submit(NewOrder(limit(1, Side.BUY, 250_000, 10)), 1)
    ex.submit(NewOrder(market(2, Side.BUY, 10)), 2)
    limit_cancel = ex.submit(CancelOrder(1), 3)
    market_cancel = ex.submit(CancelOrder(2), 4)
    assert [type(e) for e in limit_cancel] == [OrderCancelled]
    assert [type(e) for e in market_cancel] == [OrderCancelled]
    assert reject_reason(ex.submit(CancelOrder(2), 5)) is RejectReason.UNKNOWN_ORDER
    events = ex.set_session(Session.OPEN, 6)
    assert trades(events) == [] and len(ex.book) == 0


def test_modifying_a_price_in_pre_open_does_not_trade_even_if_it_crosses() -> None:
    ex = pre_open_exchange()
    ex.submit(NewOrder(limit(1, Side.BUY, 250_000, 10)), 1)
    ex.submit(NewOrder(limit(2, Side.SELL, 250_010, 10)), 2)
    events = ex.submit(ModifyOrder(2, new_price=250_000), 3)
    assert [type(e) for e in events] == [OrderModified]  # no Trade: matching waits for the auction
    assert ex.book.is_crossed()
    opened = ex.set_session(Session.OPEN, 4)
    assert trades(opened) == [(250_000, 10, 1, 2)]


def test_a_market_order_cannot_be_modified() -> None:
    ex = pre_open_exchange()
    ex.submit(NewOrder(market(1, Side.BUY, 10)), 1)
    assert reject_reason(ex.submit(ModifyOrder(1, new_quantity=5), 2)) is RejectReason.BAD_ORDER


def test_validation_still_applies_in_pre_open() -> None:
    ex = pre_open_exchange()
    assert reject_reason(ex.submit(NewOrder(limit(1, Side.BUY, 275_005, 10)), 1)) is RejectReason.OUTSIDE_BAND
    ex.submit(NewOrder(limit(2, Side.BUY, 250_000, 10)), 2)
    assert reject_reason(ex.submit(NewOrder(limit(2, Side.BUY, 250_000, 10)), 3)) is RejectReason.DUPLICATE_ORDER_ID


def test_orders_left_after_the_auction_keep_their_queue_order_and_trade_continuously() -> None:
    ex = pre_open_exchange()
    ex.submit(NewOrder(limit(1, Side.BUY, 250_000, 50)), 1)
    ex.submit(NewOrder(limit(2, Side.BUY, 250_000, 50)), 2)
    ex.submit(NewOrder(limit(3, Side.SELL, 250_000, 60)), 3)
    ex.set_session(Session.OPEN, 4)  # buyer 2 has 40 left
    events = ex.submit(NewOrder(limit(9, Side.SELL, 250_000, 40)), 5)
    assert trades(events) == [(250_000, 40, 2, 9)]
    assert len(ex.book) == 0


def test_session_transitions() -> None:
    ex = Exchange(DEMO)
    assert [type(e) for e in ex.set_session(Session.PRE_OPEN, 0)] == [SessionChanged]
    ex.set_session(Session.OPEN, 1)
    with pytest.raises(ValueError):
        ex.set_session(Session.PRE_OPEN, 2)  # pre-open can only start from a closed market
    ex.set_session(Session.CLOSED, 3)
    ex.set_session(Session.PRE_OPEN, 4)  # a new day


def test_opening_straight_from_closed_skips_the_auction() -> None:
    ex = Exchange(DEMO)
    events = ex.set_session(Session.OPEN, 1)
    assert [type(e) for e in events] == [SessionChanged]


def test_closing_during_pre_open_expires_every_order_market_orders_first() -> None:
    ex = pre_open_exchange()
    ex.submit(NewOrder(limit(1, Side.BUY, 250_000, 10)), 1)
    ex.submit(NewOrder(market(2, Side.SELL, 5)), 2)
    events = ex.set_session(Session.CLOSED, 3)
    assert [type(e) for e in events] == [SessionChanged, OrderExpired, OrderExpired]
    expired = [e for e in events if isinstance(e, OrderExpired)]
    assert [(e.order_id, e.quantity) for e in expired] == [(2, 5), (1, 10)]
    assert len(ex.book) == 0
