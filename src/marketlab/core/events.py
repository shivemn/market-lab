"""Events: the record of everything the exchange does.

Every change to the market is one event. The exchange gives each event a gapless sequence number and the
logical time at which it happened. Week 4 adds writing these to a log and replaying them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from marketlab.core.types import OrderType, RejectReason, Session, Side, TimeInForce


class CancelReason(Enum):
    USER = "USER"  # the trader asked
    IOC_REMAINDER = "IOC_REMAINDER"  # an IOC order's unfilled part
    MARKET_REMAINDER = "MARKET_REMAINDER"  # a market order's unfilled part


@dataclass(frozen=True, slots=True)
class Event:
    seq: int  # 1, 2, 3, ... with no gaps
    sim_time: int  # logical time in microseconds


@dataclass(frozen=True, slots=True)
class SessionChanged(Event):
    session: Session


@dataclass(frozen=True, slots=True)
class OrderAccepted(Event):
    order_id: int
    account_id: str
    symbol: str
    side: Side
    order_type: OrderType
    quantity: int
    limit_price: int | None
    tif: TimeInForce


@dataclass(frozen=True, slots=True)
class OrderRejected(Event):
    order_id: int
    reason: RejectReason


@dataclass(frozen=True, slots=True)
class OrderCancelled(Event):
    order_id: int
    quantity: int  # how many shares were still unfilled
    reason: CancelReason


@dataclass(frozen=True, slots=True)
class OrderModified(Event):
    order_id: int
    new_quantity: int  # total quantity, including anything already filled
    new_price: int
    remaining: int  # unfilled quantity after the change
    lost_priority: bool  # True if the order went to the back of its queue


@dataclass(frozen=True, slots=True)
class OrderExpired(Event):
    order_id: int
    quantity: int  # shares that were still unfilled when the session closed


@dataclass(frozen=True, slots=True)
class Trade(Event):
    trade_id: int
    symbol: str
    price: int  # always the resting order's price
    quantity: int
    buy_order_id: int
    sell_order_id: int
    buy_account_id: str
    sell_account_id: str
    aggressor_side: Side  # the side of the order that arrived and caused the trade
