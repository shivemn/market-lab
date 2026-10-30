"""Basic building blocks: enums, instruments and orders.

Money is stored in paise (1 rupee = 100 paise) and quantity in shares. Both are plain integers, never floats,
so rounding can never create or destroy money.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class TimeInForce(Enum):
    DAY = "DAY"  # rests on the book until filled, cancelled or the session ends
    IOC = "IOC"  # fill what is possible now, cancel the rest


class Session(Enum):
    CLOSED = "CLOSED"
    PRE_OPEN = "PRE_OPEN"
    OPEN = "OPEN"


class RejectReason(Enum):
    UNKNOWN_SYMBOL = "UNKNOWN_SYMBOL"
    MARKET_CLOSED = "MARKET_CLOSED"
    BAD_ORDER = "BAD_ORDER"  # malformed: a limit order without a price, or a market order with one
    BAD_QUANTITY = "BAD_QUANTITY"  # zero or negative
    BAD_LOT = "BAD_LOT"
    BAD_TICK = "BAD_TICK"
    OUTSIDE_BAND = "OUTSIDE_BAND"
    NO_LIQUIDITY = "NO_LIQUIDITY"  # market order and the other side of the book is empty
    UNKNOWN_ORDER = "UNKNOWN_ORDER"  # cancel or modify of an order that is not resting
    DUPLICATE_ORDER_ID = "DUPLICATE_ORDER_ID"  # the id was used before, even if that order is gone


@dataclass(frozen=True)
class Instrument:
    """A tradable stock and its rules.

    tick_size: smallest price step, in paise (5 means 5 paise).
    lot_size: order quantity must be a multiple of this.
    reference_price: previous close, in paise. Must itself be a valid price.
    band_pct: the price may move this many percent either side of the reference price.
    """

    symbol: str
    tick_size: int
    lot_size: int
    reference_price: int
    band_pct: int

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.tick_size <= 0:
            raise ValueError("tick_size must be positive")
        if self.lot_size <= 0:
            raise ValueError("lot_size must be positive")
        if self.reference_price <= 0 or self.reference_price % self.tick_size != 0:
            raise ValueError("reference_price must be positive and a multiple of tick_size")
        if not 0 < self.band_pct < 100:
            raise ValueError("band_pct must be between 0 and 100 (exclusive)")

    @property
    def band_low(self) -> int:
        """Lowest allowed price: reference minus the band, rounded up to a valid tick."""
        numerator = self.reference_price * (100 - self.band_pct)
        denominator = 100 * self.tick_size
        return -(-numerator // denominator) * self.tick_size

    @property
    def band_high(self) -> int:
        """Highest allowed price: reference plus the band, rounded down to a valid tick."""
        numerator = self.reference_price * (100 + self.band_pct)
        denominator = 100 * self.tick_size
        return (numerator // denominator) * self.tick_size


@dataclass(slots=True)
class Order:
    """An order. `remaining` starts equal to `quantity` and shrinks as the order is filled or reduced."""

    order_id: int
    account_id: str
    symbol: str
    side: Side
    type: OrderType
    quantity: int
    limit_price: int | None
    tif: TimeInForce
    entered_at: int  # logical time in microseconds
    remaining: int = field(init=False)

    def __post_init__(self) -> None:
        self.remaining = self.quantity
