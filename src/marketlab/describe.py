"""Plain-language one-line descriptions of events, for the command line and (later) the screen."""

from __future__ import annotations

from marketlab.core import (
    AuctionResult,
    Event,
    OrderAccepted,
    OrderCancelled,
    OrderExpired,
    OrderModified,
    OrderRejected,
    OrderType,
    SessionChanged,
    Trade,
)


def money(paise: int) -> str:
    """Paise as rupees, for example 250005 -> '2,500.05'."""
    sign = "-" if paise < 0 else ""
    rupees, rest = divmod(abs(paise), 100)
    return f"{sign}{rupees:,}.{rest:02d}"


def clock(sim_time: int) -> str:
    """Logical time in microseconds as h:mm:ss.mmm since the start of the run."""
    millis_total = sim_time // 1000
    seconds_total, millis = divmod(millis_total, 1000)
    minutes_total, seconds = divmod(seconds_total, 60)
    hours, minutes = divmod(minutes_total, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def describe(event: Event) -> str:
    head = f"#{event.seq:<7} {clock(event.sim_time)}  "
    if isinstance(event, SessionChanged):
        return head + f"SESSION   market is now {event.session.value}"
    if isinstance(event, OrderAccepted):
        price = "at market" if event.order_type is OrderType.MARKET else f"limit {money(event.limit_price or 0)}"
        return (
            head
            + f"ORDER     #{event.order_id} {event.account_id} {event.side.value} {event.quantity} {price} "
            + f"({event.tif.value})"
        )
    if isinstance(event, OrderRejected):
        return head + f"REJECTED  #{event.order_id} {event.reason.value}"
    if isinstance(event, OrderCancelled):
        return head + f"CANCELLED #{event.order_id} {event.quantity} left ({event.reason.value})"
    if isinstance(event, OrderExpired):
        return head + f"EXPIRED   #{event.order_id} {event.quantity} left at the close"
    if isinstance(event, OrderModified):
        moved = "went to the back of the queue" if event.lost_priority else "kept its place"
        return (
            head
            + f"MODIFIED  #{event.order_id} now {event.new_quantity} at {money(event.new_price)} "
            + f"({event.remaining} left, {moved})"
        )
    if isinstance(event, Trade):
        who = "auction" if event.aggressor_side is None else f"{event.aggressor_side.value} aggressor"
        return (
            head
            + f"TRADE     {event.quantity} at {money(event.price)} "
            + f"(buyer #{event.buy_order_id}, seller #{event.sell_order_id}, {who})"
        )
    if isinstance(event, AuctionResult):
        if event.price is None:
            return head + f"AUCTION   no trade, opening price is the reference {money(event.opening_price)}"
        return (
            head
            + f"AUCTION   price {money(event.price)}, {event.volume} shares "
            + f"(left over: {event.unmatched_buy} to buy, {event.unmatched_sell} to sell)"
        )
    return head + type(event).__name__
