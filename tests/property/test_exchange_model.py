"""Randomised test: the exchange must trade exactly like a deliberately simple reference model.

Hypothesis sends long random sequences of new orders (limit and market, DAY and IOC), cancels and
modifications to the real exchange and to a plain-list model written separately. After every command:

1. the trades must be identical (price, quantity, buyer, seller, in order),
2. the book must hold the same orders at the same prices in the same queue order,
3. the book must not be crossed, event sequence numbers must have no gaps, and every trade must be priced at a
   resting order's price inside the band,
4. for every order, shares traded + shares still resting must add up to its current size (no shares appear
   or vanish).

The model is slow (it re-scans a list every time) but easy to read, so it is a good referee for the
fast engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from marketlab.codec import decode_event, encode_event
from marketlab.core import (
    CancelOrder,
    Event,
    Exchange,
    ModifyOrder,
    NewOrder,
    OrderRejected,
    Session,
    Side,
    TimeInForce,
    Trade,
)
from marketlab.projection import MarketState
from tests.helpers import DEMO, limit, market

PRICES = [250_000 + 5 * step for step in range(-3, 4)]  # seven nearby price levels


@dataclass
class ModelOrder:
    order_id: int
    side: Side
    price: int
    quantity: int  # current total size
    remaining: int
    priority: int  # smaller means earlier in the queue


class Reference:
    """A plain list of resting orders and three obviously correct rules."""

    def __init__(self) -> None:
        self.resting: list[ModelOrder] = []
        self.counter = 0
        self.used_ids: set[int] = set()

    def _tick(self) -> int:
        self.counter += 1
        return self.counter

    def _trade(
        self, side: Side, limit_price: int | None, remaining: int, order_id: int
    ) -> tuple[list[tuple[int, int, int, int]], int]:
        """Match an incoming order. Returns (trades, unfilled quantity)."""
        trades: list[tuple[int, int, int, int]] = []
        while remaining > 0:
            others = [o for o in self.resting if o.side is not side]
            if limit_price is not None:
                others = [
                    o
                    for o in others
                    if (o.price <= limit_price if side is Side.BUY else o.price >= limit_price)
                ]
            if not others:
                break
            # Best price first (lowest ask for a buyer, highest bid for a seller), then earliest.
            best = min(others, key=lambda o: (o.price if side is Side.BUY else -o.price, o.priority))
            qty = min(remaining, best.remaining)
            buy_id, sell_id = (order_id, best.order_id) if side is Side.BUY else (best.order_id, order_id)
            trades.append((best.price, qty, buy_id, sell_id))
            best.remaining -= qty
            remaining -= qty
            if best.remaining == 0:
                self.resting.remove(best)
        return trades, remaining

    def new_limit(
        self, order_id: int, side: Side, price: int, qty: int, tif: TimeInForce
    ) -> list[tuple[int, int, int, int]]:
        self.used_ids.add(order_id)
        trades, left = self._trade(side, price, qty, order_id)
        if left > 0 and tif is TimeInForce.DAY:
            self.resting.append(ModelOrder(order_id, side, price, qty, left, self._tick()))
        return trades

    def can_take_market(self, side: Side) -> bool:
        return any(o.side is not side for o in self.resting)

    def new_market(self, order_id: int, side: Side, qty: int) -> list[tuple[int, int, int, int]]:
        self.used_ids.add(order_id)
        trades, _ = self._trade(side, None, qty, order_id)
        return trades

    def cancel(self, order_id: int) -> bool:
        for order in self.resting:
            if order.order_id == order_id:
                self.resting.remove(order)
                return True
        return False

    def modify(
        self, order_id: int, new_qty: int | None, new_price: int | None
    ) -> tuple[bool, list[tuple[int, int, int, int]]]:
        """Returns (was it accepted, trades)."""
        target = next((o for o in self.resting if o.order_id == order_id), None)
        if target is None or (new_qty is None and new_price is None):
            return False, []
        filled = target.quantity - target.remaining
        qty = target.quantity if new_qty is None else new_qty
        price = target.price if new_price is None else new_price
        if qty <= filled or (qty == target.quantity and price == target.price):
            return False, []
        if price == target.price and qty < target.quantity:
            target.quantity = qty
            target.remaining = qty - filled
            return True, []
        self.resting.remove(target)
        trades, left = self._trade(target.side, price, qty - filled, order_id)
        if left > 0:
            self.resting.append(ModelOrder(order_id, target.side, price, qty, left, self._tick()))
        return True, trades


def trades_of(events: list[Event]) -> list[tuple[int, int, int, int]]:
    return [(e.price, e.quantity, e.buy_order_id, e.sell_order_id) for e in events if isinstance(e, Trade)]


class ExchangeMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.ex = Exchange(DEMO)
        self.all_events: list[Event] = list(self.ex.set_session(Session.OPEN, 0))
        self.state = MarketState(DEMO)  # rebuilt from events alone
        self.state.apply_all(self.all_events)
        self.ref = Reference()
        self.clock = 0
        self.next_id = 1
        self.filled: dict[int, int] = {}

    def _send(self, command: NewOrder | CancelOrder | ModifyOrder) -> list[Event]:
        self.clock += 1
        events = self.ex.submit(command, self.clock)
        self.all_events.extend(events)
        self.state.apply_all(events)
        for event in events:
            assert decode_event(encode_event(event)) == event  # the log format loses nothing
        for trade in (e for e in events if isinstance(e, Trade)):
            for oid in (trade.buy_order_id, trade.sell_order_id):
                self.filled[oid] = self.filled.get(oid, 0) + trade.quantity
        return events

    def _new_id(self) -> int:
        order_id = self.next_id
        self.next_id += 1
        return order_id

    @rule(
        side=st.sampled_from(Side),
        price=st.sampled_from(PRICES),
        qty=st.integers(1, 200),
        tif=st.sampled_from(TimeInForce),
    )
    def new_limit_order(self, side: Side, price: int, qty: int, tif: TimeInForce) -> None:
        order_id = self._new_id()
        events = self._send(NewOrder(limit(order_id, side, price, qty, tif=tif)))
        assert trades_of(events) == self.ref.new_limit(order_id, side, price, qty, tif)

    @rule(side=st.sampled_from(Side), qty=st.integers(1, 300))
    def new_market_order(self, side: Side, qty: int) -> None:
        order_id = self._new_id()
        events = self._send(NewOrder(market(order_id, side, qty)))
        if self.ref.can_take_market(side):
            assert trades_of(events) == self.ref.new_market(order_id, side, qty)
        else:
            assert [type(e) for e in events] == [OrderRejected]
            self.ref.used_ids.add(order_id)

    @precondition(lambda self: bool(self.ref.resting))
    @rule(data=st.data())
    def cancel_a_resting_order(self, data: st.DataObject) -> None:
        order_id = data.draw(st.sampled_from(sorted(o.order_id for o in self.ref.resting)))
        events = self._send(CancelOrder(order_id))
        assert self.ref.cancel(order_id)
        assert not any(isinstance(e, OrderRejected) for e in events)

    @rule(order_id=st.integers(min_value=1, max_value=60))
    def cancel_any_id(self, order_id: int) -> None:
        events = self._send(CancelOrder(order_id))
        was_resting = self.ref.cancel(order_id)
        assert any(isinstance(e, OrderRejected) for e in events) == (not was_resting)

    @precondition(lambda self: bool(self.ref.resting))
    @rule(data=st.data())
    def modify_a_resting_order(self, data: st.DataObject) -> None:
        target = data.draw(st.sampled_from(sorted(self.ref.resting, key=lambda o: o.order_id)))
        order_id = target.order_id
        filled = target.quantity - target.remaining
        new_qty = data.draw(st.one_of(st.none(), st.integers(filled + 1, filled + 250)))
        new_price = data.draw(st.one_of(st.none(), st.sampled_from(PRICES)))
        accepted, expected = self.ref.modify(order_id, new_qty, new_price)
        events = self._send(ModifyOrder(order_id, new_quantity=new_qty, new_price=new_price))
        assert (not any(isinstance(e, OrderRejected) for e in events)) == accepted
        assert trades_of(events) == expected

    @invariant()
    def exchange_agrees_with_reference(self) -> None:
        self.ex.book.check_invariants()
        assert not self.ex.book.is_crossed()
        assert [e.seq for e in self.all_events] == list(range(1, len(self.all_events) + 1))

        # Same orders, same prices, same queue order.
        for side in (Side.BUY, Side.SELL):
            for view in self.ex.book.depth(side):
                queue = sorted(
                    (o for o in self.ref.resting if o.side is side and o.price == view.price),
                    key=lambda o: o.priority,
                )
                actual = self.ex.book.orders_at(side, view.price)
                assert [(o.order_id, o.remaining) for o in actual] == [
                    (o.order_id, o.remaining) for o in queue
                ]
        assert len(self.ex.book) == len(self.ref.resting)

        # The market rebuilt from events alone matches the live book: same levels, same queues, same sizes.
        for side in (Side.BUY, Side.SELL):
            assert self.state.depth(side) == self.ex.book.depth(side)
            for view in self.ex.book.depth(side):
                assert self.state.queue(side, view.price) == [
                    (o.order_id, o.remaining) for o in self.ex.book.orders_at(side, view.price)
                ]

        # Shares are conserved: traded + still resting = the order's current size.
        for resting in self.ref.resting:
            assert self.filled.get(resting.order_id, 0) + resting.remaining == resting.quantity

        # Every trade is at a valid price inside the band.
        for event in self.all_events:
            if isinstance(event, Trade):
                assert DEMO.band_low <= event.price <= DEMO.band_high
                assert event.quantity > 0


ExchangeMachine.TestCase.settings = settings(max_examples=250, stateful_step_count=80, deadline=None)
TestExchangeAgainstReference = ExchangeMachine.TestCase
