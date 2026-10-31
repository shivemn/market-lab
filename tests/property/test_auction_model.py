"""Randomised tests for the opening auction.

1. `compute_auction` is compared with a brute-force version that tries EVERY valid price in the band, straight from
   the written rules. The fast version only tries a few well-chosen prices, so this checks that shortcut is safe.
2. Whole auctions are run through the exchange with random orders, and the rules that must always hold are
   checked: one price, volume matches, no leftover crossing, shares conserved, no order trades outside its limit,
   and on each side better-priority orders are filled before worse ones.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from marketlab.core import (
    AuctionResult,
    CancelOrder,
    Exchange,
    Instrument,
    NewOrder,
    Order,
    OrderCancelled,
    OrderType,
    Session,
    Side,
    TimeInForce,
    Trade,
    compute_auction,
)
from tests.helpers import limit, market

# A small instrument keeps the brute force cheap: valid prices are 900 to 1100 in steps of 5.
SMALL = Instrument(symbol="DEMO1", tick_size=5, lot_size=1, reference_price=1000, band_pct=10)
PRICES = list(range(975, 1030, 5))  # concentrated near the reference so buyers and sellers often overlap


def brute_force(
    buys: list[tuple[int, int]], sells: list[tuple[int, int]], market_buy: int, market_sell: int
) -> tuple[int | None, int]:
    """Try every valid tick price and apply the written rules. Returns (price, volume)."""
    best_key: tuple[int, int, int, int] | None = None
    best: tuple[int, int] | None = None
    for price in range(SMALL.band_low, SMALL.band_high + 1, SMALL.tick_size):
        buy_qty = market_buy + sum(q for p, q in buys if p >= price)
        sell_qty = market_sell + sum(q for p, q in sells if p <= price)
        volume = min(buy_qty, sell_qty)
        key = (-volume, abs(buy_qty - sell_qty), abs(price - SMALL.reference_price), price)
        if best_key is None or key < best_key:
            best_key, best = key, (price, volume)
    assert best is not None
    return (None, 0) if best[1] == 0 else best


limit_orders = st.lists(st.tuples(st.sampled_from(PRICES), st.integers(1, 60)), max_size=8)


@settings(max_examples=500, deadline=None)
@given(
    buys=limit_orders,
    sells=limit_orders,
    market_buy=st.integers(0, 80),
    market_sell=st.integers(0, 80),
)
def test_fast_auction_matches_brute_force(
    buys: list[tuple[int, int]], sells: list[tuple[int, int]], market_buy: int, market_sell: int
) -> None:
    outcome = compute_auction(
        buy_limits=buys,
        sell_limits=sells,
        market_buy=market_buy,
        market_sell=market_sell,
        reference_price=SMALL.reference_price,
        tick_size=SMALL.tick_size,
        band_low=SMALL.band_low,
        band_high=SMALL.band_high,
    )
    assert (outcome.price, outcome.volume) == brute_force(buys, sells, market_buy, market_sell)


order_specs = st.lists(
    st.tuples(
        st.sampled_from(Side),
        st.sampled_from(["limit_day", "limit_ioc", "market"]),
        st.sampled_from(PRICES),
        st.integers(1, 60),
    ),
    max_size=12,
)


def build(order_id: int, side: Side, kind: str, price: int, qty: int) -> Order:
    if kind == "market":
        return market(order_id, side, qty)
    tif = TimeInForce.IOC if kind == "limit_ioc" else TimeInForce.DAY
    return limit(order_id, side, price, qty, tif=tif)


@settings(max_examples=400, deadline=None)
@given(specs=order_specs, cancel_mask=st.lists(st.booleans(), max_size=12))
def test_every_auction_obeys_the_rules(specs: list[tuple[Side, str, int, int]], cancel_mask: list[bool]) -> None:
    ex = Exchange(SMALL)
    ex.set_session(Session.PRE_OPEN, 0)
    orders: dict[int, Order] = {}
    clock = 0
    for index, (side, kind, price, qty) in enumerate(specs, start=1):
        clock += 1
        order = build(index, side, kind, price, qty)
        orders[index] = order
        ex.submit(NewOrder(order), clock)
    cancelled_by_user: set[int] = set()
    for index, should_cancel in enumerate(cancel_mask, start=1):
        if should_cancel and index in orders:
            clock += 1
            ex.submit(CancelOrder(index), clock)
            cancelled_by_user.add(index)

    events = ex.set_session(Session.OPEN, clock + 1)
    live = {i: o for i, o in orders.items() if i not in cancelled_by_user}

    result = events[0]
    assert isinstance(result, AuctionResult)
    trades = [e for e in events if isinstance(e, Trade)]

    # 1. One price, and the volume and price agree with the brute-force rules.
    live_limits = [(o.side, o.limit_price, o.quantity) for o in live.values() if o.limit_price is not None]
    expected_price, expected_volume = brute_force(
        [(p, q) for side, p, q in live_limits if side is Side.BUY],
        [(p, q) for side, p, q in live_limits if side is Side.SELL],
        sum(o.quantity for o in live.values() if o.type is OrderType.MARKET and o.side is Side.BUY),
        sum(o.quantity for o in live.values() if o.type is OrderType.MARKET and o.side is Side.SELL),
    )
    assert (result.price, result.volume) == (expected_price, expected_volume)
    assert result.opening_price == (expected_price if expected_price is not None else SMALL.reference_price)
    assert {t.price for t in trades} <= ({expected_price} if expected_price is not None else set())
    assert sum(t.quantity for t in trades) == expected_volume

    # 2. Nothing is left crossed, and no market or IOC order survives.
    assert not ex.book.is_crossed()
    assert all(o.tif is TimeInForce.DAY for o in ex.book.all_orders())

    # 3. Shares are conserved: filled + still resting + cancelled by the auction = the order's size.
    filled: dict[int, int] = {}
    for t in trades:
        for oid in (t.buy_order_id, t.sell_order_id):
            filled[oid] = filled.get(oid, 0) + t.quantity
    auction_cancelled = {e.order_id: e.quantity for e in events if isinstance(e, OrderCancelled)}
    for oid, order in live.items():
        resting = ex.book.get(oid)
        total = filled.get(oid, 0) + (resting.remaining if resting else 0) + auction_cancelled.get(oid, 0)
        assert total == order.quantity, f"order {oid}: {total} != {order.quantity}"

    # 4. Nobody trades outside their own limit.
    if expected_price is not None:
        for oid, order in live.items():
            if order.limit_price is None or filled.get(oid, 0) == 0:
                continue
            if order.side is Side.BUY:
                assert order.limit_price >= expected_price
            else:
                assert order.limit_price <= expected_price

        # 5. On each side, better-priority orders are filled first: once an order is not fully filled,
        #    every order behind it gets nothing. Priority: market orders, then best limit, then earliest.
        for side in (Side.BUY, Side.SELL):
            eligible = [
                o
                for o in live.values()
                if o.side is side
                and (
                    o.limit_price is None
                    or (o.limit_price >= expected_price if side is Side.BUY else o.limit_price <= expected_price)
                )
            ]

            def priority(o: Order, side: Side = side) -> tuple[int, int, int]:
                if o.limit_price is None:
                    return (0, 0, o.order_id)
                return (1, -o.limit_price if side is Side.BUY else o.limit_price, o.order_id)

            seen_partial = False
            for order in sorted(eligible, key=priority):
                done = filled.get(order.order_id, 0)
                if seen_partial:
                    assert done == 0, f"order {order.order_id} traded behind an unfilled better order"
                if done < order.quantity:
                    seen_partial = True

