"""Rebuilding the state of the market from events alone.

The exchange keeps its own order book while it runs. This module does the opposite job: it folds the stream of
events into a picture of the market (what is resting, the last price, the volume), using nothing but the events.
If the two ever disagree, the events win, because the events are the record of what happened.

This is also what a screen or an analysis tool uses. Feed events in one at a time with `apply`.

One thing to know when applying events one by one: an order is added to the picture when it is accepted, and
the trades and cancellations that follow within the same command shrink or remove it. Look at the state between
commands, not in the middle of one.
"""

from __future__ import annotations

from dataclasses import dataclass

from marketlab.core import (
    AuctionResult,
    Event,
    Instrument,
    LevelView,
    OrderAccepted,
    OrderCancelled,
    OrderExpired,
    OrderModified,
    OrderRejected,
    OrderType,
    Session,
    SessionChanged,
    Side,
    TimeInForce,
    Trade,
)


@dataclass
class RestingOrder:
    order_id: int
    account_id: str
    side: Side
    price: int
    quantity: int  # current total size
    remaining: int
    tif: TimeInForce
    priority: int  # smaller means earlier in the queue


class MarketState:
    def __init__(self, instrument: Instrument) -> None:
        self.instrument = instrument
        self.session = Session.CLOSED
        self.orders: dict[int, RestingOrder] = {}
        self.pending_market: dict[int, int] = {}  # market orders waiting for the opening auction: id -> remaining
        self.opening_price: int | None = None
        self.last_price: int | None = None
        self.high: int | None = None
        self.low: int | None = None
        self.trades = 0
        self.volume = 0
        self.events_applied = 0
        self._priority = 0

    # ---- applying events ----

    def apply(self, event: Event) -> None:
        self.events_applied += 1
        if isinstance(event, SessionChanged):
            self.session = event.session
        elif isinstance(event, OrderAccepted):
            self._accepted(event)
        elif isinstance(event, OrderModified):
            self._modified(event)
        elif isinstance(event, Trade):
            self._traded(event)
        elif isinstance(event, (OrderCancelled, OrderExpired)):
            self.orders.pop(event.order_id, None)
            self.pending_market.pop(event.order_id, None)
        elif isinstance(event, AuctionResult):
            self.opening_price = event.opening_price
        elif isinstance(event, OrderRejected):
            pass  # a rejection changes nothing

    def apply_all(self, events: list[Event]) -> None:
        for event in events:
            self.apply(event)

    def _accepted(self, event: OrderAccepted) -> None:
        if event.order_type is OrderType.LIMIT:
            assert event.limit_price is not None
            self._priority += 1
            self.orders[event.order_id] = RestingOrder(
                event.order_id,
                event.account_id,
                event.side,
                event.limit_price,
                event.quantity,
                event.quantity,
                event.tif,
                self._priority,
            )
        elif self.session is Session.PRE_OPEN:
            self.pending_market[event.order_id] = event.quantity

    def _modified(self, event: OrderModified) -> None:
        order = self.orders.get(event.order_id)
        if order is None:
            return
        order.quantity = event.new_quantity
        order.price = event.new_price
        order.remaining = event.remaining
        if event.lost_priority:
            self._priority += 1
            order.priority = self._priority

    def _traded(self, event: Trade) -> None:
        self.trades += 1
        self.volume += event.quantity
        self.last_price = event.price
        self.high = event.price if self.high is None else max(self.high, event.price)
        self.low = event.price if self.low is None else min(self.low, event.price)
        for order_id in (event.buy_order_id, event.sell_order_id):
            order = self.orders.get(order_id)
            if order is not None:
                order.remaining -= event.quantity
                if order.remaining <= 0:
                    del self.orders[order_id]
                continue
            waiting = self.pending_market.get(order_id)
            if waiting is not None:
                waiting -= event.quantity
                if waiting <= 0:
                    del self.pending_market[order_id]
                else:
                    self.pending_market[order_id] = waiting

    # ---- reading the picture ----

    def depth(self, side: Side, levels: int | None = None) -> list[LevelView]:
        """Price levels on one side, best price first."""
        totals: dict[int, list[int]] = {}
        for order in self.orders.values():
            if order.side is side:
                entry = totals.setdefault(order.price, [0, 0])
                entry[0] += order.remaining
                entry[1] += 1
        prices = sorted(totals, reverse=(side is Side.BUY))
        views = [LevelView(price, totals[price][0], totals[price][1]) for price in prices]
        return views if levels is None else views[:levels]

    def queue(self, side: Side, price: int) -> list[tuple[int, int]]:
        """(order id, remaining) at one price, in time priority."""
        at_price = [o for o in self.orders.values() if o.side is side and o.price == price]
        return [(o.order_id, o.remaining) for o in sorted(at_price, key=lambda o: o.priority)]

    def best_bid(self) -> int | None:
        bids = self.depth(Side.BUY, 1)
        return bids[0].price if bids else None

    def best_ask(self) -> int | None:
        asks = self.depth(Side.SELL, 1)
        return asks[0].price if asks else None
