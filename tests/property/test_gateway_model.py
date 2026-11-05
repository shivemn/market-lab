"""A practice account trading against random other traders on a real exchange.

After every step the books must agree with the gateway and with the exchange, and when the day is over the ledger
built live (reserving and settling as orders trade) must equal one rebuilt from the log alone with `post_trades`.
Both routes must end with the same cash, shares and charges, whatever the random orders did.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from marketlab.core import CancelOrder, Event, Exchange, NewOrder, Order, Session, Side, TimeInForce
from marketlab.costs import PLANS, CostModel, schedule_on
from marketlab.ledger import Gateway, Ledger, OrderRefused, locked_account, post_trades, reserved_account
from tests.helpers import DEMO, limit, market

ME = "YOU"
side = st.sampled_from([Side.BUY, Side.SELL])
offset = st.integers(min_value=-6, max_value=6)  # ticks away from the reference price
quantity = st.integers(min_value=1, max_value=25)

step = st.one_of(
    st.tuples(st.just("other_limit"), side, offset, quantity),
    st.tuples(st.just("other_market"), side, quantity),
    st.tuples(st.just("me_limit"), side, offset, quantity, st.sampled_from([TimeInForce.DAY, TimeInForce.IOC])),
    st.tuples(st.just("me_market"), side, quantity),
    st.tuples(st.just("me_cancel"), st.integers(min_value=0, max_value=50)),
)


def price(ticks: int) -> int:
    return DEMO.reference_price + ticks * DEMO.tick_size


def nonzero(ledger: Ledger, skip: tuple[str, ...] = ()) -> dict[str, int]:
    return {a: b for a, b in ledger.balances().items() if b != 0 and not a.startswith(skip)}


@settings(max_examples=150, deadline=None)
@given(steps=st.lists(step, max_size=40), plan=st.sampled_from(sorted(PLANS)))
def test_live_gateway_and_rebuild_from_the_log_agree(steps: list[Any], plan: str) -> None:
    costs = CostModel(schedule_on(date(2026, 11, 1)), PLANS[plan])
    ledger = Ledger()
    ledger.open_account(ME, starting_cash=10_000_000)
    ledger.grant_shares(ME, "DEMO1", 100)
    exchange = Exchange(DEMO, Session.OPEN)
    gateway = Gateway(ledger, ME, DEMO, costs)
    events: list[Event] = []
    clock = 0
    next_id = 0

    def send(order: Order) -> None:
        nonlocal clock
        clock += 1
        new = exchange.submit(NewOrder(order), clock)
        events.extend(new)
        gateway.settle(new)

    for op in steps:
        next_id += 1
        kind = op[0]
        if kind == "other_limit":
            send(limit(next_id, op[1], price(op[2]), op[3], account="X"))
        elif kind == "other_market":
            send(market(next_id, op[1], op[2], account="X"))
        elif kind in ("me_limit", "me_market"):
            order = (
                limit(next_id, op[1], price(op[2]), op[3], account=ME, tif=op[4])
                if kind == "me_limit"
                else market(next_id, op[1], op[2], account=ME)
            )
            try:
                gateway.reserve(order)
            except OrderRefused:
                continue
            send(order)
        else:
            live = gateway.open_order_ids()
            if live:
                clock += 1
                new = exchange.submit(CancelOrder(live[op[1] % len(live)]), clock)
                events.extend(new)
                gateway.settle(new)

        # what the gateway says is set aside is exactly what the ledger holds
        assert ledger.balance(reserved_account(ME)) == gateway.reserved_cash()
        assert ledger.balance(locked_account(ME, "DEMO1")) == gateway.locked_shares()
        # and the open orders are exactly my orders still resting on the exchange
        resting = {o.order_id for o in exchange.book.all_orders() if o.account_id == ME}
        assert set(gateway.open_order_ids()) == resting
        assert ledger.verify() == []

    for order_id in gateway.open_order_ids():
        clock += 1
        new = exchange.submit(CancelOrder(order_id), clock)
        events.extend(new)
        gateway.settle(new)
    assert gateway.open_order_ids() == []
    assert ledger.balance(reserved_account(ME)) == 0
    assert ledger.balance(locked_account(ME, "DEMO1")) == 0

    rebuilt = Ledger()
    rebuilt.open_account(ME, starting_cash=10_000_000)
    rebuilt.grant_shares(ME, "DEMO1", 100)
    post_trades(rebuilt, events, source="day", tracked=lambda a: a == ME, costs=costs)
    assert nonzero(ledger) == nonzero(rebuilt)
