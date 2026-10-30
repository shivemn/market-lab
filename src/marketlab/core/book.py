"""The order book for one instrument.

Resting orders are grouped into price levels. Within a level, orders keep the order they arrived in (time
priority). Between levels, the best price comes first: the highest bid and the lowest ask.

Week 1 provides the data structure: resting, cancelling, reducing and reading the book.
Matching comes in Week 2.
"""

from __future__ import annotations

from bisect import bisect_left, insort
from collections import OrderedDict
from typing import NamedTuple

from marketlab.core.types import Order, OrderType, Side


class LevelView(NamedTuple):
    """A read-only summary of one price level."""

    price: int
    quantity: int  # total remaining quantity at this price
    orders: int  # number of orders at this price


class _Level:
    __slots__ = ("orders", "total")

    def __init__(self) -> None:
        # OrderedDict keeps arrival order, removes any order in O(1) and reads the oldest in O(1).
        self.orders: OrderedDict[int, Order] = OrderedDict()
        self.total = 0


class OrderBook:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self._levels: dict[Side, dict[int, _Level]] = {Side.BUY: {}, Side.SELL: {}}
        # Sorted ascending. Best bid is the last price, best ask is the first.
        self._prices: dict[Side, list[int]] = {Side.BUY: [], Side.SELL: []}
        self._orders: dict[int, Order] = {}

    # ---- changes ----

    def rest(self, order: Order) -> None:
        """Put a limit order on the book at the back of its price level."""
        if order.type is not OrderType.LIMIT or order.limit_price is None:
            raise ValueError("only limit orders with a price can rest on the book")
        if order.symbol != self.symbol:
            raise ValueError("order is for a different symbol")
        if order.remaining <= 0:
            raise ValueError("order has nothing remaining")
        if order.order_id in self._orders:
            raise ValueError(f"duplicate order id {order.order_id}")

        price = order.limit_price
        levels = self._levels[order.side]
        level = levels.get(price)
        if level is None:
            level = _Level()
            levels[price] = level
            insort(self._prices[order.side], price)
        level.orders[order.order_id] = order
        level.total += order.remaining
        self._orders[order.order_id] = order

    def cancel(self, order_id: int) -> Order | None:
        """Remove a resting order and return it, or return None if it is not on the book."""
        order = self._orders.pop(order_id, None)
        if order is None:
            return None
        assert order.limit_price is not None
        self._remove_from_level(order)
        return order

    def reduce(self, order_id: int, new_remaining: int) -> Order | None:
        """Lower an order's remaining quantity while keeping its place in the queue.

        Returns the order, or None if it is not on the book. The new quantity must be above zero and below
        the current remaining quantity. To remove an order entirely, use cancel.
        """
        order = self._orders.get(order_id)
        if order is None:
            return None
        if new_remaining <= 0 or new_remaining >= order.remaining:
            raise ValueError("new_remaining must be above zero and below the current remaining quantity")
        assert order.limit_price is not None
        level = self._levels[order.side][order.limit_price]
        level.total -= order.remaining - new_remaining
        order.remaining = new_remaining
        return order

    def fill(self, order_id: int, quantity: int) -> Order:
        """Take `quantity` shares from a resting order because it traded.

        The order keeps its place in the queue unless it is fully filled, in which case it leaves the book.
        """
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(order_id)
        if quantity <= 0 or quantity > order.remaining:
            raise ValueError("fill quantity must be above zero and at most the remaining quantity")
        assert order.limit_price is not None
        if quantity == order.remaining:
            del self._orders[order_id]
            self._remove_from_level(order)  # uses order.remaining, so it must run before the line below
            order.remaining = 0
        else:
            self._levels[order.side][order.limit_price].total -= quantity
            order.remaining -= quantity
        return order

    # ---- reading ----

    def get(self, order_id: int) -> Order | None:
        return self._orders.get(order_id)

    def peek_best(self, side: Side) -> Order | None:
        """The order that would trade first on this side: best price, then oldest."""
        prices = self._prices[side]
        if not prices:
            return None
        best_price = prices[-1] if side is Side.BUY else prices[0]
        return next(iter(self._levels[side][best_price].orders.values()))

    def all_orders(self) -> list[Order]:
        """Every resting order in a fixed order: bids then asks, best price first, oldest first."""
        result: list[Order] = []
        for side in (Side.BUY, Side.SELL):
            for view in self.depth(side):
                result.extend(self._levels[side][view.price].orders.values())
        return result

    def best_bid(self) -> int | None:
        prices = self._prices[Side.BUY]
        return prices[-1] if prices else None

    def best_ask(self) -> int | None:
        prices = self._prices[Side.SELL]
        return prices[0] if prices else None

    def is_crossed(self) -> bool:
        bid, ask = self.best_bid(), self.best_ask()
        return bid is not None and ask is not None and bid >= ask

    def depth(self, side: Side, levels: int | None = None) -> list[LevelView]:
        """Price levels on one side, best price first."""
        prices = self._prices[side]
        ordered = reversed(prices) if side is Side.BUY else iter(prices)
        result: list[LevelView] = []
        for price in ordered:
            if levels is not None and len(result) >= levels:
                break
            level = self._levels[side][price]
            result.append(LevelView(price, level.total, len(level.orders)))
        return result

    def orders_at(self, side: Side, price: int) -> list[Order]:
        """Orders at one price level, in time priority (oldest first)."""
        level = self._levels[side].get(price)
        return list(level.orders.values()) if level else []

    def __len__(self) -> int:
        return len(self._orders)

    def __contains__(self, order_id: int) -> bool:
        return order_id in self._orders

    # ---- internals ----

    def _remove_from_level(self, order: Order) -> None:
        assert order.limit_price is not None
        price = order.limit_price
        levels = self._levels[order.side]
        level = levels[price]
        del level.orders[order.order_id]
        level.total -= order.remaining
        if not level.orders:
            del levels[price]
            prices = self._prices[order.side]
            index = bisect_left(prices, price)
            del prices[index]

    def check_invariants(self) -> None:
        """Raise AssertionError if the book is internally inconsistent. Used by tests."""
        seen = 0
        for side in (Side.BUY, Side.SELL):
            prices = self._prices[side]
            levels = self._levels[side]
            assert prices == sorted(set(prices)), "price list must be sorted and unique"
            assert set(prices) == set(levels), "price list and levels must match"
            for price, level in levels.items():
                assert level.orders, "empty level left behind"
                assert level.total == sum(o.remaining for o in level.orders.values()), "level total wrong"
                for order in level.orders.values():
                    assert order.side is side and order.limit_price == price, "order in wrong level"
                    assert order.remaining > 0, "resting order with nothing remaining"
                    assert self._orders.get(order.order_id) is order, "order index out of date"
                seen += len(level.orders)
        assert seen == len(self._orders), "order index has orders that are not in any level"
