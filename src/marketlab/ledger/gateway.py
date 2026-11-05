"""Checks before an order reaches the exchange, and the paperwork as it trades.

Without this, three buy orders could each look affordable and together not be. So when a practice order is placed:

- a buy sets aside its worst-case cost: price x quantity plus the highest charges it could incur. A market order has
  no price, so it is set aside at the top of the price band, and the refusal message says so;
- a sell locks the shares it offers, so the same shares cannot be sold twice. It also sets aside the fixed fees of
  the broker plan (nothing, on the default plan), because the first fill carries them.

As the order trades, each fill pays from what was set aside. A buy that fills at a better price than its limit
frees the difference. When the order ends (fully filled, cancelled, expired, or rejected by the exchange) whatever
is left goes back to the owner. The money and shares stay in the ledger the whole time, in "reserved" and "locked"
accounts, so nothing is ever outside the books.

The gateway lives as long as a practice session. It remembers its open orders in memory; the ledger keeps the
balances. Changing an open order is not supported yet: cancel it and place a new one.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from marketlab.core import (
    Event,
    Instrument,
    Order,
    OrderCancelled,
    OrderExpired,
    OrderModified,
    OrderRejected,
    OrderType,
    Side,
    Trade,
)
from marketlab.costs import CostModel
from marketlab.describe import rupees
from marketlab.ledger.ledger import Entry, Ledger, LedgerError
from marketlab.ledger.names import (
    INR,
    MARKET_CASH,
    cash_account,
    cost_account,
    locked_account,
    market_shares_account,
    reserved_account,
    shares_account,
)


class OrderRefused(LedgerError):
    """The order was not sent to the exchange. The message says why, in words a learner can act on."""


@dataclass(slots=True)
class _Reservation:
    order_id: int
    side: Side
    quantity: int
    cash: int  # paise still set aside for this order
    shares: int  # shares still locked for this order
    filled: int = 0
    traded_value: int = 0


class Gateway:
    def __init__(self, ledger: Ledger, owner: str, instrument: Instrument, costs: CostModel) -> None:
        self._ledger = ledger
        self._owner = owner
        self._instrument = instrument
        self._costs = costs
        self._open: dict[int, _Reservation] = {}
        ledger.balance(cash_account(owner))  # the account must have been opened
        ledger.ensure_account(reserved_account(owner), INR)
        ledger.ensure_account(shares_account(owner, instrument.symbol), instrument.symbol)
        ledger.ensure_account(locked_account(owner, instrument.symbol), instrument.symbol)
        ledger.ensure_account(market_shares_account(instrument.symbol), instrument.symbol, allows_negative=True)

    def recover(self) -> int:
        """Give back money and shares left set aside by a session that never finished (a crash, or a closed tab).

        Only safe when no other gateway is running for this owner, which is why a session ends the old one first.
        Returns how many paise were returned.
        """
        owner, symbol = self._owner, self._instrument.symbol
        cash = self._ledger.balance(reserved_account(owner)) - self.reserved_cash()
        shares = self._ledger.balance(locked_account(owner, symbol)) - self.locked_shares()
        entries: list[Entry] = []
        if cash:
            entries += [Entry(reserved_account(owner), -cash), Entry(cash_account(owner), cash)]
        if shares:
            entries += [Entry(locked_account(owner, symbol), -shares), Entry(shares_account(owner, symbol), shares)]
        if entries:
            self._ledger.post(entries, at=0, memo="Returned from a session that did not finish")
        return cash

    def abandon(self) -> None:
        """End the session early: return everything still set aside for open orders."""
        for reservation in list(self._open.values()):
            self._open.pop(reservation.order_id, None)
            self._release(reservation, 0)

    # -- reading ----------------------------------------------------------------------------------------------

    def open_order_ids(self) -> list[int]:
        return sorted(self._open)

    def reserved_cash(self) -> int:
        """What the gateway believes is set aside. The ledger's reserved account must always agree."""
        return sum(r.cash for r in self._open.values())

    def locked_shares(self) -> int:
        return sum(r.shares for r in self._open.values())

    def available_cash(self) -> int:
        return self._ledger.cash(self._owner)

    def available_shares(self) -> int:
        return self._ledger.shares(self._owner, self._instrument.symbol)

    # -- before the exchange ----------------------------------------------------------------------------------

    def worst_case_cost(self, order: Order) -> int:
        """The most a buy could cost, charges included. A market order is priced at the top of the band."""
        price = order.limit_price if order.type is OrderType.LIMIT else self._instrument.band_high
        assert price is not None
        value = price * order.quantity
        return value + self._costs.for_order(Side.BUY, value).total

    def fixed_fees(self) -> int:
        """Brokerage and demat fees (with GST on them) that a sell must be able to pay. Zero on the default plan."""
        plan = self._costs.plan
        fixed = plan.brokerage_per_order + plan.demat_per_sell_order
        return fixed + self._costs.schedule.gst.of(fixed) if fixed else 0

    def reserve(self, order: Order) -> None:
        """Check the order and set money or shares aside. Raises OrderRefused, changing nothing, if it cannot."""
        if order.account_id != self._owner or order.symbol != self._instrument.symbol:
            raise OrderRefused("this order is not for this account or this stock")
        if order.order_id in self._open:
            raise OrderRefused(f"order {order.order_id} is already open")
        owner, symbol = self._owner, self._instrument.symbol
        if order.side is Side.BUY:
            need = self.worst_case_cost(order)
            have = self.available_cash()
            if need > have:
                how = (
                    f"{rupees(self._instrument.band_high)} a share, the top of today's price band, because a market "
                    "order has no price of its own"
                    if order.type is OrderType.MARKET
                    else f"{rupees(order.limit_price or 0)} a share"
                )
                raise OrderRefused(
                    f"You have {rupees(have)} available, but this order could cost up to {rupees(need)} "
                    f"({order.quantity} shares at {how}, plus charges). Money already set aside for your other open "
                    "orders is not available."
                )
            self._ledger.post(
                [Entry(cash_account(owner), -need), Entry(reserved_account(owner), need)],
                at=order.entered_at,
                memo=f"Set aside for buy order {order.order_id}",
            )
            self._open[order.order_id] = _Reservation(order.order_id, Side.BUY, order.quantity, cash=need, shares=0)
            return

        held = self.available_shares()
        if order.quantity > held:
            locked = self.locked_shares()
            raise OrderRefused(
                f"You have {held} {symbol} shares free to sell, but this order sells {order.quantity}."
                + (f" {locked} more are locked in your other open sell orders." if locked else "")
            )
        fees = self.fixed_fees()
        if fees > self.available_cash():
            raise OrderRefused(
                f"Selling needs {rupees(fees)} in cash to pay the broker's fees, and you have "
                f"{rupees(self.available_cash())} available."
            )
        entries = [
            Entry(shares_account(owner, symbol), -order.quantity),
            Entry(locked_account(owner, symbol), order.quantity),
        ]
        if fees:
            entries += [Entry(cash_account(owner), -fees), Entry(reserved_account(owner), fees)]
        self._ledger.post(entries, at=order.entered_at, memo=f"Locked for sell order {order.order_id}")
        self._open[order.order_id] = _Reservation(
            order.order_id, Side.SELL, order.quantity, cash=fees, shares=order.quantity
        )

    # -- after the exchange -----------------------------------------------------------------------------------

    def settle(self, events: Iterable[Event]) -> None:
        """Read what the exchange did and update the ledger. Give it every event, in order; it skips others' orders."""
        for event in events:
            if isinstance(event, Trade):
                for order_id in (event.buy_order_id, event.sell_order_id):
                    reservation = self._open.get(order_id)
                    if reservation is not None:
                        self._fill(reservation, event)
            elif isinstance(event, OrderRejected | OrderCancelled | OrderExpired):
                reservation = self._open.pop(event.order_id, None)
                if reservation is not None:
                    self._release(reservation, event.sim_time)
            elif isinstance(event, OrderModified) and event.order_id in self._open:
                raise LedgerError("changing an open practice order is not supported yet: cancel it and place a new one")

    def _fill(self, reservation: _Reservation, trade: Trade) -> None:
        owner, symbol = self._owner, self._instrument.symbol
        value = trade.price * trade.quantity
        charges = self._costs.for_new_fill(reservation.side, reservation.traded_value, value)
        buying = reservation.side is Side.BUY
        due = (value if buying else 0) + charges.total
        from_reserved = min(due, reservation.cash)
        from_cash = due - from_reserved  # nothing for a buy; for a sell, the charges beyond the set-aside fees
        entries = [
            Entry(reserved_account(owner), -from_reserved),
            Entry(cash_account(owner), -from_cash),
        ]
        for line, amount in charges.lines():
            if amount:
                entries.append(Entry(cost_account(line), amount))
        if buying:
            entries += [
                Entry(MARKET_CASH, value),
                Entry(shares_account(owner, symbol), trade.quantity),
                Entry(market_shares_account(symbol), -trade.quantity),
            ]
        else:
            entries += [
                Entry(cash_account(owner), value),
                Entry(MARKET_CASH, -value),
                Entry(locked_account(owner, symbol), -trade.quantity),
                Entry(market_shares_account(symbol), trade.quantity),
            ]
        side = "Bought" if buying else "Sold"
        self._ledger.post(
            entries,
            at=trade.sim_time,
            memo=f"{side} {trade.quantity} {symbol} at {trade.price} paise (order {reservation.order_id})",
        )
        reservation.cash -= from_reserved
        if not buying:
            reservation.shares -= trade.quantity
        reservation.filled += trade.quantity
        reservation.traded_value += value
        if reservation.filled >= reservation.quantity:
            self._open.pop(reservation.order_id, None)
            self._release(reservation, trade.sim_time)

    def _release(self, reservation: _Reservation, at: int) -> None:
        """Give back whatever is still set aside for an order that has ended."""
        owner, symbol = self._owner, self._instrument.symbol
        entries: list[Entry] = []
        if reservation.cash:
            entries += [Entry(reserved_account(owner), -reservation.cash), Entry(cash_account(owner), reservation.cash)]
        if reservation.shares:
            entries += [
                Entry(locked_account(owner, symbol), -reservation.shares),
                Entry(shares_account(owner, symbol), reservation.shares),
            ]
        if entries:
            self._ledger.post(entries, at=at, memo=f"Released what was left for order {reservation.order_id}")
