"""A practice session: one simulated day, one practice account, orders you place yourself.

This ties together the stepping simulation, the ledger and the gateway. The server never keeps a clock. The day
moves only when `advance` is called, so the caller (the browser) owns speed and pause. `advance` stops early when
one of your orders trades, so the page can stop and explain what happened.

Refused orders never reach the exchange, draw no random numbers and change nothing, so they do not change the day.
The commands that were sent are remembered with their simulated times, and `replay` re-runs the day from them and
must give the same fingerprint and the same books.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from marketlab.codec import hash_events
from marketlab.core import CancelOrder, Event, NewOrder, Order, OrderType, Side, TimeInForce, Trade
from marketlab.costs import PLANS, CostModel, schedule_on
from marketlab.ledger import STARTING_CASH, Gateway, Ledger, OrderRefused, locked_account, reserved_account
from marketlab.sim import SimConfig, Simulation, replay_with_commands

MICROS = 1_000_000


@dataclass(frozen=True, slots=True)
class OpenOrder:
    order_id: int
    side: Side
    quantity: int
    remaining: int
    limit_price: int | None


@dataclass(frozen=True, slots=True)
class Portfolio:
    cash: int  # paise free to use
    reserved: int  # paise set aside for open orders
    shares: int  # free to sell
    locked: int  # set aside for open sell orders
    open_orders: tuple[OpenOrder, ...]


@dataclass(frozen=True, slots=True)
class Advance:
    events: list[Event]
    now: int
    stopped_for_fill: bool  # the day paused early because one of your orders traded
    finished: bool


class PracticeSession:
    def __init__(
        self,
        config: SimConfig,
        ledger: Ledger,
        owner: str,
        *,
        plan: str = "zero",
        trading_date: date | None = None,
        starting_cash: int = STARTING_CASH,
    ) -> None:
        self.config = config
        self.owner = owner
        self.ledger = ledger
        self.sim = Simulation(config)
        ledger.open_account(owner, starting_cash=starting_cash)
        self.costs = CostModel(schedule_on(trading_date or date.today()), PLANS[plan])
        self.gateway = Gateway(ledger, owner, self.sim.instrument, self.costs)
        self.gateway.recover()
        self._sent: dict[int, Order] = {}
        self.gateway.settle(self.sim.events)

    # -- the day ----------------------------------------------------------------------------------------------

    @property
    def now(self) -> int:
        return self.sim.now

    @property
    def finished(self) -> bool:
        return self.sim.finished

    def _mine(self, events: list[Event]) -> bool:
        return any(isinstance(e, Trade) and self.owner in (e.buy_account_id, e.sell_account_id) for e in events)

    def advance(self, seconds: float, *, pause_on_fill: bool = True) -> Advance:
        if seconds < 0:
            raise ValueError("cannot move the day backwards")
        target = self.sim.now + round(seconds * MICROS)
        events = self.sim.advance_to(target, self._mine if pause_on_fill else None)
        self.gateway.settle(events)
        stopped = not self.sim.finished and self.sim.now < min(target, self.sim.close_at)
        return Advance(events, self.sim.now, stopped, self.sim.finished)

    # -- my orders --------------------------------------------------------------------------------------------

    def place(
        self,
        side: Side,
        quantity: int,
        limit_price: int | None = None,
        tif: TimeInForce = TimeInForce.DAY,
    ) -> tuple[int, list[Event]]:
        """Check, set aside, send. Raises OrderRefused (changing nothing) when the order cannot be placed."""
        if self.sim.finished:
            raise OrderRefused("the market is closed for the day")
        if quantity <= 0:
            raise OrderRefused("the quantity must be at least 1 share")
        order = Order(
            order_id=self.sim.new_user_order_id(),
            account_id=self.owner,
            symbol=self.sim.instrument.symbol,
            side=side,
            type=OrderType.LIMIT if limit_price is not None else OrderType.MARKET,
            quantity=quantity,
            limit_price=limit_price,
            tif=tif,
            entered_at=self.sim.now,
        )
        self.gateway.reserve(order)
        self._sent[order.order_id] = order
        events = self.sim.inject(NewOrder(order))
        self.gateway.settle(events)
        return order.order_id, events

    def cancel(self, order_id: int) -> list[Event]:
        if self.sim.finished:
            raise OrderRefused("the market is closed for the day")
        if order_id not in self.gateway.open_order_ids():
            raise OrderRefused(f"order {order_id} is not open")
        events = self.sim.inject(CancelOrder(order_id))
        self.gateway.settle(events)
        return events

    def end_early(self) -> None:
        """Leave the day: cancel nothing on the exchange (the day is over for this session) and free the money."""
        self.gateway.abandon()

    # -- looking ----------------------------------------------------------------------------------------------

    def portfolio(self) -> Portfolio:
        symbol = self.sim.instrument.symbol
        resting = {o.order_id: o for o in self.sim.exchange.book.all_orders() if o.account_id == self.owner}
        pending = self.sim.state.pending_market  # market orders waiting for the opening auction
        orders: list[OpenOrder] = []
        for order_id in self.gateway.open_order_ids():
            sent = self._sent[order_id]
            left = resting[order_id].remaining if order_id in resting else pending.get(order_id, sent.quantity)
            orders.append(OpenOrder(order_id, sent.side, sent.quantity, left, sent.limit_price))
        return Portfolio(
            cash=self.ledger.cash(self.owner),
            reserved=self.ledger.balance(reserved_account(self.owner)),
            shares=self.ledger.shares(self.owner, symbol),
            locked=self.ledger.balance(locked_account(self.owner, symbol)),
            open_orders=tuple(orders),
        )

    def fingerprint(self) -> str:
        return hash_events(self.sim.events)


def replay(session: PracticeSession) -> Simulation:
    """Re-run a session's day from its seed and the commands that were sent. Must match the original exactly."""
    return replay_with_commands(session.config, session.sim.script)
