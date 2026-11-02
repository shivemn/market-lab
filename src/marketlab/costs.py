"""What a delivery trade costs in India, worked out exactly in whole paise.

Every rate is a fraction of whole numbers, never a float, so a cost is the same on every machine and can be checked
by hand. A rate of "Rs 307 per crore" is `Rate(307, 10_000_000)`. Amounts are rounded to the nearest paisa, with
exact halves rounded up. Real brokers round in slightly different places, so a contract note can differ from this
by a paisa or two; the size of the charges is what matters here.

Two things are kept apart on purpose:

- `ChargeSchedule`: government and exchange charges. Everyone pays the same, they change on known dates, and each
  schedule records where its numbers come from.
- `BrokerPlan`: what a broker adds (brokerage, and a demat fee on sales). This is the part that differs.

Scope for now: delivery equity on the NSE, one order at a time. Intraday and other products come later.
These are teaching numbers, not tax or investment advice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from marketlab.core import Side

CRORE = 10_000_000  # rupees


@dataclass(frozen=True, slots=True)
class Rate:
    """A fraction of a trade's value: numerator / denominator."""

    numerator: int
    denominator: int

    def of(self, amount: int) -> int:
        """The rate applied to `amount` (paise), rounded to the nearest paisa, halves up."""
        return (2 * amount * self.numerator + self.denominator) // (2 * self.denominator)

    def percent(self) -> str:
        return f"{self.numerator * 100 / self.denominator:g}%"


def per_crore(rupees: int) -> Rate:
    """`Rs rupees` for every Rs 1 crore traded."""
    return Rate(rupees, CRORE)


@dataclass(frozen=True, slots=True)
class ChargeSchedule:
    effective_from: date
    stt_buy: Rate
    stt_sell: Rate
    exchange: Rate  # NSE transaction charge, which now includes the investor protection fund contribution
    sebi: Rate
    stamp_buy: Rate
    gst: Rate  # applied to brokerage, the demat fee, the exchange charge and the SEBI fee (not to STT or stamp duty)
    source: str


@dataclass(frozen=True, slots=True)
class BrokerPlan:
    name: str
    brokerage_per_order: int  # paise, charged once per order that trades
    demat_per_sell_order: int  # paise, charged once per sell order that trades (a simplification, see below)
    description: str


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    brokerage: int = 0
    stt: int = 0
    exchange: int = 0
    sebi: int = 0
    stamp: int = 0
    demat: int = 0
    gst: int = 0

    @property
    def total(self) -> int:
        return self.brokerage + self.stt + self.exchange + self.sebi + self.stamp + self.demat + self.gst

    def lines(self) -> list[tuple[str, int]]:
        return [
            ("brokerage", self.brokerage),
            ("stt", self.stt),
            ("exchange", self.exchange),
            ("sebi", self.sebi),
            ("stamp", self.stamp),
            ("demat", self.demat),
            ("gst", self.gst),
        ]

    def minus(self, other: CostBreakdown) -> CostBreakdown:
        return CostBreakdown(
            self.brokerage - other.brokerage,
            self.stt - other.stt,
            self.exchange - other.exchange,
            self.sebi - other.sebi,
            self.stamp - other.stamp,
            self.demat - other.demat,
            self.gst - other.gst,
        )


# -- the schedules, newest last ----------------------------------------------------------------------------------

_SECONDARY = (
    "STT 0.1% on both sides, stamp duty 0.015% on the buy side, SEBI fee Rs 10 per crore and GST 18% are as listed by "
    "broker pages (Upstox, Rupeezy, checked November 2026), not read from the statutes."
)

SCHEDULES: list[ChargeSchedule] = [
    ChargeSchedule(
        effective_from=date(2024, 10, 1),
        stt_buy=Rate(1, 1000),
        stt_sell=Rate(1, 1000),
        exchange=per_crore(297),
        sebi=per_crore(10),
        stamp_buy=Rate(15, 100_000),
        gst=Rate(18, 100),
        source="NSE transaction charge Rs 297 per crore as listed by Upstox for 1 Oct 2024 to 28 Feb 2026. "
        + _SECONDARY,
    ),
    ChargeSchedule(
        effective_from=date(2026, 3, 1),
        stt_buy=Rate(1, 1000),
        stt_sell=Rate(1, 1000),
        exchange=per_crore(307),
        sebi=per_crore(10),
        stamp_buy=Rate(15, 100_000),
        gst=Rate(18, 100),
        source=(
            "NSE transaction charge Rs 307 per crore each side (Rs 306.99 plus Rs 0.01 to the IPFT) from NSE circular "
            "NSE/FA/73061 dated 27 Feb 2026, effective 1 Mar 2026. " + _SECONDARY
        ),
    ),
]

PLANS: dict[str, BrokerPlan] = {
    "zero": BrokerPlan(
        "zero",
        0,
        0,
        "No brokerage and no demat fee, as many discount brokers offer on delivery. Only the statutory and exchange "
        "charges remain.",
    ),
    "flat20": BrokerPlan(
        "flat20",
        2000,
        2000,
        "Rs 20 per executed order and Rs 20 demat fee per sell order, the figures Upstox listed for delivery in "
        "November 2026. Real demat fees are per share-holding per day, and brokers differ.",
    ),
}


def schedule_on(day: date) -> ChargeSchedule:
    """The charges in force on a given day."""
    current = [s for s in SCHEDULES if s.effective_from <= day]
    if not current:
        raise ValueError(f"no charge schedule is recorded for {day}; the earliest starts {SCHEDULES[0].effective_from}")
    return current[-1]


def order_costs(side: Side, value: int, schedule: ChargeSchedule, plan: BrokerPlan) -> CostBreakdown:
    """The costs of one whole order whose fills add up to `value` paise. No fills, no costs."""
    if value < 0:
        raise ValueError("value cannot be negative")
    if value == 0:
        return CostBreakdown()
    buying = side is Side.BUY
    brokerage = plan.brokerage_per_order
    demat = 0 if buying else plan.demat_per_sell_order
    exchange = schedule.exchange.of(value)
    sebi = schedule.sebi.of(value)
    return CostBreakdown(
        brokerage=brokerage,
        stt=(schedule.stt_buy if buying else schedule.stt_sell).of(value),
        exchange=exchange,
        sebi=sebi,
        stamp=schedule.stamp_buy.of(value) if buying else 0,
        demat=demat,
        gst=schedule.gst.of(brokerage + demat + exchange + sebi),
    )


@dataclass(frozen=True, slots=True)
class CostModel:
    """The charges and the broker plan that apply to a trading day."""

    schedule: ChargeSchedule
    plan: BrokerPlan

    def for_order(self, side: Side, value: int) -> CostBreakdown:
        return order_costs(side, value, self.schedule, self.plan)

    def for_new_fill(self, side: Side, value_before: int, fill_value: int) -> CostBreakdown:
        """What a new fill adds to an order's costs, so that the fills' costs always add up to the order's cost.

        Charges are worked out on everything the order has traded so far and the part already charged is taken
        off. This makes the total independent of how the order was split into fills, and a flat brokerage lands
        on the first fill.
        """
        return self.for_order(side, value_before + fill_value).minus(self.for_order(side, value_before))
