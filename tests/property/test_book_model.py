"""Randomised test: the order book must always agree with a deliberately simple model.

Hypothesis performs long random sequences of rest, cancel and reduce operations. After every step the
book's own consistency check runs, and its prices, queues and quantities are compared with a plain
dictionary model.
The model is slow but obviously correct, which is what makes it a useful referee.
"""

from __future__ import annotations

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from marketlab.core import LevelView, OrderBook, Side
from tests.helpers import limit

PRICES = [250_000 + 5 * step for step in range(-3, 4)]  # seven nearby price levels


class BookMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.book = OrderBook("DEMO1")
        # order id -> (side, price, remaining). Insertion order is the time priority.
        self.model: dict[int, tuple[Side, int, int]] = {}
        self.next_id = 1

    @rule(side=st.sampled_from(Side), price=st.sampled_from(PRICES), quantity=st.integers(1, 1_000))
    def rest(self, side: Side, price: int, quantity: int) -> None:
        order_id = self.next_id
        self.next_id += 1
        self.book.rest(limit(order_id, side, price, quantity))
        self.model[order_id] = (side, price, quantity)

    @precondition(lambda self: bool(self.model))
    @rule(data=st.data())
    def cancel_existing(self, data: st.DataObject) -> None:
        order_id = data.draw(st.sampled_from(sorted(self.model)))
        cancelled = self.book.cancel(order_id)
        assert cancelled is not None and cancelled.order_id == order_id
        del self.model[order_id]

    @rule(order_id=st.integers(min_value=-5, max_value=10_000))
    def cancel_anything(self, order_id: int) -> None:
        cancelled = self.book.cancel(order_id)
        if order_id in self.model:
            assert cancelled is not None
            del self.model[order_id]
        else:
            assert cancelled is None

    @precondition(lambda self: any(rem > 1 for _, _, rem in self.model.values()))
    @rule(data=st.data())
    def reduce_existing(self, data: st.DataObject) -> None:
        reducible = sorted(oid for oid, (_, _, rem) in self.model.items() if rem > 1)
        order_id = data.draw(st.sampled_from(reducible))
        side, price, remaining = self.model[order_id]
        new_remaining = data.draw(st.integers(1, remaining - 1))
        reduced = self.book.reduce(order_id, new_remaining)
        assert reduced is not None and reduced.remaining == new_remaining
        self.model[order_id] = (side, price, new_remaining)  # same dict slot: priority unchanged

    def expected_depth(self, side: Side) -> list[LevelView]:
        by_price: dict[int, list[int]] = {}
        for entry_side, price, remaining in self.model.values():
            if entry_side is side:
                by_price.setdefault(price, []).append(remaining)
        prices = sorted(by_price, reverse=(side is Side.BUY))
        return [LevelView(p, sum(by_price[p]), len(by_price[p])) for p in prices]

    @invariant()
    def book_matches_model(self) -> None:
        self.book.check_invariants()
        assert len(self.book) == len(self.model)
        for side in (Side.BUY, Side.SELL):
            expected = self.expected_depth(side)
            assert self.book.depth(side) == expected
            for view in expected:
                queue = [oid for oid, (s, p, _) in self.model.items() if s is side and p == view.price]
                assert [o.order_id for o in self.book.orders_at(side, view.price)] == queue
        expected_bids = self.expected_depth(Side.BUY)
        expected_asks = self.expected_depth(Side.SELL)
        assert self.book.best_bid() == (expected_bids[0].price if expected_bids else None)
        assert self.book.best_ask() == (expected_asks[0].price if expected_asks else None)


BookMachine.TestCase.settings = settings(max_examples=200, stateful_step_count=60, deadline=None)
TestBookAgainstModel = BookMachine.TestCase
