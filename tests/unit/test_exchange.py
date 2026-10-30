"""Hand-calculated examples for the matching engine.

Reference price is 250000 paise (2,500.00 rupees), tick 5, band 225000 to 275000.
"""

from __future__ import annotations

import pytest

from marketlab.core import (
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


def open_exchange() -> Exchange:
    exchange = Exchange(DEMO)
    exchange.set_session(Session.OPEN, 0)
    return exchange


def trades(events: list[Event]) -> list[tuple[int, int, int, int]]:
    """(price, quantity, buy order id, sell order id) for each trade."""
    return [(e.price, e.quantity, e.buy_order_id, e.sell_order_id) for e in events if isinstance(e, Trade)]


def reject_reason(events: list[Event]) -> RejectReason:
    rejected = [e for e in events if isinstance(e, OrderRejected)]
    assert len(rejected) == 1
    return rejected[0].reason


def test_non_crossing_limit_order_rests_and_does_not_trade() -> None:
    ex = open_exchange()
    events = ex.submit(NewOrder(limit(1, Side.BUY, 249_990, 10)), 1)
    assert [type(e) for e in events] == [OrderAccepted]
    assert ex.book.depth(Side.BUY) == [LevelView(249_990, 10, 1)]
    events = ex.submit(NewOrder(limit(2, Side.SELL, 250_010, 10)), 2)
    assert trades(events) == []
    assert ex.book.best_bid() == 249_990 and ex.book.best_ask() == 250_010


def test_buy_sweeps_two_price_levels_and_trades_at_each_resting_price() -> None:
    ex = open_exchange()
    ex.submit(NewOrder(limit(1, Side.SELL, 250_010, 10)), 1)
    ex.submit(NewOrder(limit(2, Side.SELL, 250_015, 20)), 2)
    events = ex.submit(NewOrder(limit(3, Side.BUY, 250_020, 25)), 3)
    assert trades(events) == [(250_010, 10, 3, 1), (250_015, 15, 3, 2)]
    # The buyer is fully filled, so nothing rests on the bid side. 5 shares remain at 250015.
    assert ex.book.depth(Side.BUY) == []
    assert ex.book.depth(Side.SELL) == [LevelView(250_015, 5, 1)]


def test_trade_price_is_the_resting_price_not_the_incoming_price() -> None:
    ex = open_exchange()
    ex.submit(NewOrder(limit(1, Side.SELL, 250_010, 10)), 1)
    events = ex.submit(NewOrder(limit(2, Side.BUY, 250_100, 10)), 2)
    assert trades(events) == [(250_010, 10, 2, 1)]
    ex.submit(NewOrder(limit(3, Side.BUY, 249_900, 10)), 3)
    events = ex.submit(NewOrder(limit(4, Side.SELL, 249_800, 10)), 4)
    assert trades(events) == [(249_900, 10, 3, 4)]


def test_same_price_orders_fill_oldest_first() -> None:
    ex = open_exchange()
    for order_id, when in ((1, 1), (2, 2), (3, 3)):
        ex.submit(NewOrder(limit(order_id, Side.SELL, 250_010, 10)), when)
    events = ex.submit(NewOrder(limit(4, Side.BUY, 250_010, 25)), 4)
    assert trades(events) == [(250_010, 10, 4, 1), (250_010, 10, 4, 2), (250_010, 5, 4, 3)]


def test_partly_filled_resting_order_keeps_its_place_in_the_queue() -> None:
    ex = open_exchange()
    ex.submit(NewOrder(limit(1, Side.SELL, 250_010, 100)), 1)
    ex.submit(NewOrder(limit(2, Side.SELL, 250_010, 100)), 2)
    events = ex.submit(NewOrder(limit(3, Side.BUY, 250_010, 30)), 3)
    assert trades(events) == [(250_010, 30, 3, 1)]
    assert [(o.order_id, o.remaining) for o in ex.book.orders_at(Side.SELL, 250_010)] == [(1, 70), (2, 100)]
    events = ex.submit(NewOrder(limit(4, Side.BUY, 250_010, 80)), 4)
    assert trades(events) == [(250_010, 70, 4, 1), (250_010, 10, 4, 2)]


def test_unfilled_part_of_a_day_order_rests_at_its_own_limit_price() -> None:
    ex = open_exchange()
    ex.submit(NewOrder(limit(1, Side.SELL, 250_010, 10)), 1)
    events = ex.submit(NewOrder(limit(2, Side.BUY, 250_010, 30)), 2)
    assert trades(events) == [(250_010, 10, 2, 1)]
    assert ex.book.depth(Side.BUY) == [LevelView(250_010, 20, 1)]
    assert ex.book.depth(Side.SELL) == []
    assert not ex.book.is_crossed()


def test_ioc_order_cancels_its_unfilled_part() -> None:
    ex = open_exchange()
    ex.submit(NewOrder(limit(1, Side.SELL, 250_010, 10)), 1)
    events = ex.submit(NewOrder(limit(2, Side.BUY, 250_010, 30, tif=TimeInForce.IOC)), 2)
    assert trades(events) == [(250_010, 10, 2, 1)]
    cancelled = [e for e in events if isinstance(e, OrderCancelled)]
    assert [(c.order_id, c.quantity, c.reason) for c in cancelled] == [(2, 20, CancelReason.IOC_REMAINDER)]
    assert ex.book.depth(Side.BUY) == []


def test_ioc_order_that_cannot_trade_is_accepted_then_cancelled_in_full() -> None:
    ex = open_exchange()
    events = ex.submit(NewOrder(limit(1, Side.BUY, 250_000, 10, tif=TimeInForce.IOC)), 1)
    assert [type(e) for e in events] == [OrderAccepted, OrderCancelled]
    assert ex.book.depth(Side.BUY) == []


def test_market_order_sweeps_levels_and_cancels_the_rest() -> None:
    ex = open_exchange()
    ex.submit(NewOrder(limit(1, Side.SELL, 250_010, 10)), 1)
    ex.submit(NewOrder(limit(2, Side.SELL, 250_020, 10)), 2)
    events = ex.submit(NewOrder(market(3, Side.BUY, 50)), 3)
    assert trades(events) == [(250_010, 10, 3, 1), (250_020, 10, 3, 2)]
    cancelled = [e for e in events if isinstance(e, OrderCancelled)]
    assert [(c.quantity, c.reason) for c in cancelled] == [(30, CancelReason.MARKET_REMAINDER)]
    assert len(ex.book) == 0


def test_market_order_into_an_empty_side_is_rejected() -> None:
    ex = open_exchange()
    events = ex.submit(NewOrder(market(1, Side.BUY, 10)), 1)
    assert reject_reason(events) is RejectReason.NO_LIQUIDITY
    assert [type(e) for e in events] == [OrderRejected]


def test_validation_failures_are_rejected_without_touching_the_book() -> None:
    ex = open_exchange()
    ex.submit(NewOrder(limit(1, Side.SELL, 250_010, 10)), 1)
    assert reject_reason(ex.submit(NewOrder(limit(2, Side.BUY, 250_003, 1)), 2)) is RejectReason.BAD_TICK
    assert reject_reason(ex.submit(NewOrder(limit(3, Side.BUY, 300_000, 1)), 3)) is RejectReason.OUTSIDE_BAND
    assert ex.book.depth(Side.SELL) == [LevelView(250_010, 10, 1)]


def test_an_order_id_can_never_be_reused() -> None:
    ex = open_exchange()
    ex.submit(NewOrder(limit(1, Side.BUY, 250_000, 10)), 1)
    again = NewOrder(limit(1, Side.BUY, 249_995, 10))
    assert reject_reason(ex.submit(again, 2)) is RejectReason.DUPLICATE_ORDER_ID
    ex.submit(CancelOrder(1), 3)
    assert reject_reason(ex.submit(again, 4)) is RejectReason.DUPLICATE_ORDER_ID  # even after a cancel


def test_cancel_removes_the_order_and_reports_the_unfilled_quantity() -> None:
    ex = open_exchange()
    ex.submit(NewOrder(limit(1, Side.BUY, 250_000, 100)), 1)
    ex.submit(NewOrder(limit(2, Side.SELL, 250_000, 40)), 2)  # fills 40 of order 1
    events = ex.submit(CancelOrder(1), 3)
    assert [(e.order_id, e.quantity, e.reason) for e in events if isinstance(e, OrderCancelled)] == [
        (1, 60, CancelReason.USER)
    ]
    assert len(ex.book) == 0


def test_cancelling_an_unknown_or_finished_order_is_rejected() -> None:
    ex = open_exchange()
    assert reject_reason(ex.submit(CancelOrder(99), 1)) is RejectReason.UNKNOWN_ORDER
    ex.submit(NewOrder(limit(1, Side.BUY, 250_000, 10)), 2)
    ex.submit(NewOrder(limit(2, Side.SELL, 250_000, 10)), 3)  # order 1 is fully filled
    assert reject_reason(ex.submit(CancelOrder(1), 4)) is RejectReason.UNKNOWN_ORDER


def test_modify_lower_quantity_keeps_priority() -> None:
    ex = open_exchange()
    ex.submit(NewOrder(limit(1, Side.SELL, 250_010, 100)), 1)
    ex.submit(NewOrder(limit(2, Side.SELL, 250_010, 100)), 2)
    events = ex.submit(ModifyOrder(1, new_quantity=40), 3)
    modified = [e for e in events if isinstance(e, OrderModified)]
    assert [(m.new_quantity, m.remaining, m.lost_priority) for m in modified] == [(40, 40, False)]
    assert [o.order_id for o in ex.book.orders_at(Side.SELL, 250_010)] == [1, 2]
    assert ex.book.depth(Side.SELL) == [LevelView(250_010, 140, 2)]


def test_modify_new_price_loses_priority() -> None:
    ex = open_exchange()
    ex.submit(NewOrder(limit(1, Side.SELL, 250_010, 100)), 1)
    ex.submit(NewOrder(limit(2, Side.SELL, 250_020, 100)), 2)
    ex.submit(ModifyOrder(2, new_price=250_010), 3)
    assert [o.order_id for o in ex.book.orders_at(Side.SELL, 250_010)] == [1, 2]
    ex.submit(ModifyOrder(1, new_price=250_015), 4)
    ex.submit(ModifyOrder(1, new_price=250_010), 5)  # back to the old price, but at the back of the queue
    assert [o.order_id for o in ex.book.orders_at(Side.SELL, 250_010)] == [2, 1]


def test_modify_higher_quantity_loses_priority() -> None:
    ex = open_exchange()
    ex.submit(NewOrder(limit(1, Side.SELL, 250_010, 100)), 1)
    ex.submit(NewOrder(limit(2, Side.SELL, 250_010, 100)), 2)
    events = ex.submit(ModifyOrder(1, new_quantity=150), 3)
    assert [m.lost_priority for m in events if isinstance(m, OrderModified)] == [True]
    assert [(o.order_id, o.remaining) for o in ex.book.orders_at(Side.SELL, 250_010)] == [(2, 100), (1, 150)]


def test_modify_to_a_price_that_crosses_trades_at_once() -> None:
    ex = open_exchange()
    ex.submit(NewOrder(limit(1, Side.SELL, 250_020, 10)), 1)
    ex.submit(NewOrder(limit(2, Side.BUY, 250_000, 25)), 2)
    events = ex.submit(ModifyOrder(2, new_price=250_030), 3)
    assert [type(e) for e in events] == [OrderModified, Trade]
    assert trades(events) == [(250_020, 10, 2, 1)]
    assert ex.book.depth(Side.BUY) == [LevelView(250_030, 15, 1)]


def test_modify_counts_the_quantity_already_filled() -> None:
    ex = open_exchange()
    ex.submit(NewOrder(limit(1, Side.BUY, 250_000, 100)), 1)
    ex.submit(NewOrder(limit(2, Side.SELL, 250_000, 60)), 2)  # order 1 now has 40 left, 60 filled
    # A new total of 60 or less would leave nothing unfilled (60 are already done), so it is refused.
    assert reject_reason(ex.submit(ModifyOrder(1, new_quantity=60), 3)) is RejectReason.BAD_QUANTITY
    assert reject_reason(ex.submit(ModifyOrder(1, new_quantity=50), 4)) is RejectReason.BAD_QUANTITY
    # A new total of 70 leaves 10 unfilled, and lowering the size keeps the place in the queue.
    events = ex.submit(ModifyOrder(1, new_quantity=70), 5)
    assert [type(e) for e in events] == [OrderModified]
    modified = events[0]
    assert isinstance(modified, OrderModified)
    assert modified.new_quantity == 70 and modified.remaining == 10 and not modified.lost_priority
    order = ex.book.get(1)
    assert order is not None and order.quantity == 70 and order.remaining == 10


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, RejectReason.BAD_ORDER),
        ({"new_quantity": 100}, RejectReason.BAD_ORDER),  # nothing would change
        ({"new_price": 250_000}, RejectReason.BAD_ORDER),  # nothing would change
        ({"new_price": 250_003}, RejectReason.BAD_TICK),
        ({"new_price": 300_000}, RejectReason.OUTSIDE_BAND),
        ({"new_quantity": 0}, RejectReason.BAD_QUANTITY),
    ],
)
def test_bad_modifications_are_rejected(kwargs: dict[str, int], expected: RejectReason) -> None:
    ex = open_exchange()
    ex.submit(NewOrder(limit(1, Side.BUY, 250_000, 100)), 1)
    assert reject_reason(ex.submit(ModifyOrder(1, **kwargs), 2)) is expected
    order = ex.book.get(1)
    assert order is not None and (order.quantity, order.remaining, order.limit_price) == (100, 100, 250_000)


def test_modifying_an_unknown_order_is_rejected() -> None:
    ex = open_exchange()
    assert reject_reason(ex.submit(ModifyOrder(7, new_quantity=5), 1)) is RejectReason.UNKNOWN_ORDER


def test_closed_market_rejects_everything() -> None:
    ex = Exchange(DEMO)
    new_order = NewOrder(limit(1, Side.BUY, 250_000, 10))
    assert reject_reason(ex.submit(new_order, 1)) is RejectReason.MARKET_CLOSED
    assert reject_reason(ex.submit(CancelOrder(1), 2)) is RejectReason.MARKET_CLOSED
    assert reject_reason(ex.submit(ModifyOrder(1, new_quantity=5), 3)) is RejectReason.MARKET_CLOSED


def test_closing_the_market_expires_resting_orders_in_a_fixed_order() -> None:
    ex = open_exchange()
    ex.submit(NewOrder(limit(1, Side.BUY, 249_990, 10)), 1)
    ex.submit(NewOrder(limit(2, Side.BUY, 250_000, 20)), 2)
    ex.submit(NewOrder(limit(3, Side.BUY, 250_000, 30)), 3)
    ex.submit(NewOrder(limit(4, Side.SELL, 250_020, 40)), 4)
    events = ex.set_session(Session.CLOSED, 5)
    assert isinstance(events[0], SessionChanged) and events[0].session is Session.CLOSED
    expired = [(e.order_id, e.quantity) for e in events if isinstance(e, OrderExpired)]
    # Bids first, best price first, oldest first. Then asks.
    assert expired == [(2, 20), (3, 30), (1, 10), (4, 40)]
    assert len(ex.book) == 0


def test_setting_the_same_session_again_is_an_error() -> None:
    ex = open_exchange()
    with pytest.raises(ValueError):
        ex.set_session(Session.OPEN, 1)


def test_time_cannot_go_backwards() -> None:
    ex = open_exchange()
    ex.submit(NewOrder(limit(1, Side.BUY, 250_000, 10)), 100)
    with pytest.raises(ValueError):
        ex.submit(NewOrder(limit(2, Side.BUY, 250_000, 10)), 99)


def test_sequence_numbers_are_gapless_and_time_is_recorded() -> None:
    ex = Exchange(DEMO)
    events = ex.set_session(Session.OPEN, 10)
    events += ex.submit(NewOrder(limit(1, Side.SELL, 250_010, 10)), 11)
    events += ex.submit(NewOrder(limit(2, Side.BUY, 250_010, 10)), 12)
    events += ex.submit(CancelOrder(5), 12)
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert [e.sim_time for e in events] == sorted(e.sim_time for e in events)
