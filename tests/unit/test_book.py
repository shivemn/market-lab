from __future__ import annotations

import pytest

from marketlab.core import LevelView, OrderBook, Side
from tests.helpers import limit, market


def test_empty_book() -> None:
    book = OrderBook("DEMO1")
    assert book.best_bid() is None
    assert book.best_ask() is None
    assert book.depth(Side.BUY) == []
    assert book.depth(Side.SELL) == []
    assert len(book) == 0
    assert not book.is_crossed()


def test_best_prices_are_highest_bid_and_lowest_ask() -> None:
    book = OrderBook("DEMO1")
    book.rest(limit(1, Side.BUY, 249_990, 10))
    book.rest(limit(2, Side.BUY, 250_000, 10))
    book.rest(limit(3, Side.BUY, 249_995, 10))
    book.rest(limit(4, Side.SELL, 250_020, 10))
    book.rest(limit(5, Side.SELL, 250_010, 10))
    assert book.best_bid() == 250_000
    assert book.best_ask() == 250_010
    book.check_invariants()


def test_depth_adds_up_each_level_and_lists_best_price_first() -> None:
    book = OrderBook("DEMO1")
    book.rest(limit(1, Side.BUY, 250_000, 10))
    book.rest(limit(2, Side.BUY, 250_000, 25))
    book.rest(limit(3, Side.BUY, 249_995, 40))
    book.rest(limit(4, Side.SELL, 250_010, 5))
    book.rest(limit(5, Side.SELL, 250_015, 7))
    book.rest(limit(6, Side.SELL, 250_015, 3))
    assert book.depth(Side.BUY) == [LevelView(250_000, 35, 2), LevelView(249_995, 40, 1)]
    assert book.depth(Side.SELL) == [LevelView(250_010, 5, 1), LevelView(250_015, 10, 2)]
    assert book.depth(Side.BUY, levels=1) == [LevelView(250_000, 35, 2)]


def test_orders_at_a_price_keep_arrival_order() -> None:
    book = OrderBook("DEMO1")
    for order_id in (7, 3, 9, 1):
        book.rest(limit(order_id, Side.BUY, 250_000, 10))
    assert [o.order_id for o in book.orders_at(Side.BUY, 250_000)] == [7, 3, 9, 1]


def test_cancel_in_the_middle_keeps_the_rest_in_order() -> None:
    book = OrderBook("DEMO1")
    for order_id in (1, 2, 3, 4):
        book.rest(limit(order_id, Side.BUY, 250_000, 10))
    cancelled = book.cancel(3)
    assert cancelled is not None and cancelled.order_id == 3
    assert [o.order_id for o in book.orders_at(Side.BUY, 250_000)] == [1, 2, 4]
    assert book.depth(Side.BUY) == [LevelView(250_000, 30, 3)]
    assert 3 not in book
    book.check_invariants()


def test_cancelling_the_last_order_removes_the_price_level() -> None:
    book = OrderBook("DEMO1")
    book.rest(limit(1, Side.BUY, 250_000, 10))
    book.rest(limit(2, Side.BUY, 249_995, 10))
    book.cancel(1)
    assert book.best_bid() == 249_995
    assert book.depth(Side.BUY) == [LevelView(249_995, 10, 1)]
    book.cancel(2)
    assert book.best_bid() is None
    assert len(book) == 0
    book.check_invariants()


def test_cancel_unknown_order_returns_none() -> None:
    book = OrderBook("DEMO1")
    assert book.cancel(42) is None
    book.rest(limit(1, Side.BUY, 250_000, 10))
    book.cancel(1)
    assert book.cancel(1) is None  # already gone


def test_reduce_keeps_the_place_in_the_queue() -> None:
    book = OrderBook("DEMO1")
    for order_id in (1, 2, 3):
        book.rest(limit(order_id, Side.SELL, 250_010, 100))
    reduced = book.reduce(1, 40)
    assert reduced is not None and reduced.remaining == 40
    assert [o.order_id for o in book.orders_at(Side.SELL, 250_010)] == [1, 2, 3]
    assert book.depth(Side.SELL) == [LevelView(250_010, 240, 3)]
    book.check_invariants()


@pytest.mark.parametrize("new_remaining", [0, -1, 100, 101])
def test_reduce_rejects_values_that_are_not_a_reduction(new_remaining: int) -> None:
    book = OrderBook("DEMO1")
    book.rest(limit(1, Side.BUY, 250_000, 100))
    with pytest.raises(ValueError):
        book.reduce(1, new_remaining)
    assert book.get(1) is not None and book.get(1).remaining == 100  # type: ignore[union-attr]


def test_reduce_unknown_order_returns_none() -> None:
    assert OrderBook("DEMO1").reduce(5, 1) is None


def test_duplicate_order_id_is_refused() -> None:
    book = OrderBook("DEMO1")
    book.rest(limit(1, Side.BUY, 250_000, 10))
    with pytest.raises(ValueError):
        book.rest(limit(1, Side.SELL, 250_100, 10))


def test_market_orders_cannot_rest() -> None:
    with pytest.raises(ValueError):
        OrderBook("DEMO1").rest(market(1, Side.BUY, 10))


def test_orders_for_another_symbol_are_refused() -> None:
    with pytest.raises(ValueError):
        OrderBook("DEMO1").rest(limit(1, Side.BUY, 250_000, 10, symbol="OTHER"))


def test_order_with_nothing_remaining_is_refused() -> None:
    order = limit(1, Side.BUY, 250_000, 10)
    order.remaining = 0
    with pytest.raises(ValueError):
        OrderBook("DEMO1").rest(order)


def test_is_crossed_detects_overlapping_prices() -> None:
    # Matching does not exist yet, so a crossed book can be built by hand to test the check itself.
    book = OrderBook("DEMO1")
    book.rest(limit(1, Side.BUY, 250_010, 10))
    book.rest(limit(2, Side.SELL, 250_010, 10))
    assert book.is_crossed()
