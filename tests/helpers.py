"""Small helpers shared by the tests."""

from __future__ import annotations

from marketlab.core import Instrument, Order, OrderType, Side, TimeInForce

# Reference price 2,500.00 rupees = 250000 paise. Tick 5 paise. Band 10 percent: 225000 to 275000.
DEMO = Instrument(symbol="DEMO1", tick_size=5, lot_size=1, reference_price=250_000, band_pct=10)


def limit(
    order_id: int,
    side: Side,
    price: int,
    quantity: int,
    *,
    account: str = "A",
    tif: TimeInForce = TimeInForce.DAY,
    entered_at: int = 0,
    symbol: str = "DEMO1",
) -> Order:
    return Order(
        order_id=order_id,
        account_id=account,
        symbol=symbol,
        side=side,
        type=OrderType.LIMIT,
        quantity=quantity,
        limit_price=price,
        tif=tif,
        entered_at=entered_at,
    )


def market(
    order_id: int,
    side: Side,
    quantity: int,
    *,
    account: str = "A",
    entered_at: int = 0,
    symbol: str = "DEMO1",
) -> Order:
    return Order(
        order_id=order_id,
        account_id=account,
        symbol=symbol,
        side=side,
        type=OrderType.MARKET,
        quantity=quantity,
        limit_price=None,
        tif=TimeInForce.IOC,
        entered_at=entered_at,
    )
