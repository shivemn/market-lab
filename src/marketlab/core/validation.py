"""Order validation. Returns the first reason an order must be rejected, or None if it is acceptable.

The checks run in a fixed order, so the same bad order always gets the same reason.
"""

from __future__ import annotations

from marketlab.core.types import Instrument, Order, OrderType, RejectReason, Session


def check_quantity(instrument: Instrument, quantity: int) -> RejectReason | None:
    if quantity <= 0:
        return RejectReason.BAD_QUANTITY
    if quantity % instrument.lot_size != 0:
        return RejectReason.BAD_LOT
    return None


def check_price(instrument: Instrument, price: int) -> RejectReason | None:
    if price % instrument.tick_size != 0:
        return RejectReason.BAD_TICK
    if price < instrument.band_low or price > instrument.band_high:
        return RejectReason.OUTSIDE_BAND
    return None


def validate_order(
    order: Order, instrument: Instrument | None, session: Session
) -> RejectReason | None:
    if instrument is None or instrument.symbol != order.symbol:
        return RejectReason.UNKNOWN_SYMBOL
    if session is Session.CLOSED:
        return RejectReason.MARKET_CLOSED

    if order.type is OrderType.LIMIT and order.limit_price is None:
        return RejectReason.BAD_ORDER
    if order.type is OrderType.MARKET and order.limit_price is not None:
        return RejectReason.BAD_ORDER

    reason = check_quantity(instrument, order.quantity)
    if reason is not None:
        return reason
    if order.limit_price is not None:
        return check_price(instrument, order.limit_price)
    return None
