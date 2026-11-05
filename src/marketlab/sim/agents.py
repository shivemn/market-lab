"""Simulated traders.

Three kinds, each simple on purpose:

- MarketMaker: keeps one buy and one sell quote either side of what it believes the stock is worth, and
  refreshes them. It provides the queue other people trade against.
- NoiseTrader: trades for no reason, at random times, in random directions and sizes (mostly small, sometimes
  large). It supplies the flow that makes the book move.
- ValueTrader: has a noisy view of the true value and trades when the market price is clearly away from it.
  It pulls the price back towards fair value.

Each trader wakes at random times (a Poisson process), looks at the market through `Context`, and returns the
commands it wants to send. Traders never touch the exchange directly.

Known simplifications (fixed in a later phase when accounts exist): traders have no cash or inventory limits.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from marketlab.core import (
    CancelOrder,
    Command,
    Instrument,
    NewOrder,
    Order,
    OrderType,
    Session,
    Side,
    TimeInForce,
)
from marketlab.projection import MarketState
from marketlab.sim.rng import SimRng


@dataclass
class Context:
    """What a trader can see and use when it wakes."""

    now: int
    instrument: Instrument
    state: MarketState  # the market as rebuilt from events: what a screen would show
    fair: float  # the true value; traders add their own error before using it
    rng: SimRng
    next_id: Callable[[], int]

    @property
    def tick(self) -> int:
        return self.instrument.tick_size

    def reference(self) -> float:
        """A price to anchor on: the middle of the best quotes, else the last trade, else the reference price."""
        bid, ask = self.state.best_bid(), self.state.best_ask()
        if bid is not None and ask is not None and self.state.session is Session.OPEN:
            return (bid + ask) / 2
        if self.state.last_price is not None:
            return float(self.state.last_price)
        if self.state.opening_price is not None:
            return float(self.state.opening_price)
        return float(self.instrument.reference_price)

    def clamp(self, price: int) -> int:
        return min(max(price, self.instrument.band_low), self.instrument.band_high)

    def round_down(self, price: float) -> int:
        return self.clamp(int(price // self.tick) * self.tick)

    def round_up(self, price: float) -> int:
        return self.clamp(-int(-price // self.tick) * self.tick)

    def order(
        self,
        account_id: str,
        side: Side,
        quantity: int,
        price: int | None,
        tif: TimeInForce = TimeInForce.DAY,
    ) -> NewOrder:
        kind = OrderType.LIMIT if price is not None else OrderType.MARKET
        return NewOrder(
            Order(
                order_id=self.next_id(),
                account_id=account_id,
                symbol=self.instrument.symbol,
                side=side,
                type=kind,
                quantity=quantity,
                limit_price=price,
                tif=tif,
                entered_at=self.now,
            )
        )


class Trader:
    """Base class: an account, a wake-up rate and an `act` method."""

    def __init__(self, account_id: str, rate: float) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self.account_id = account_id
        self.rate = rate  # average wake-ups per second
        self._live: list[int] = []  # ids of this trader's orders that may still be resting

    def delay(self, rng: SimRng) -> int:
        """Microseconds until the next wake-up."""
        return max(1, int(rng.exponential(self.rate) * 1_000_000))

    def act(self, ctx: Context) -> list[Command]:
        raise NotImplementedError

    def _still_resting(self, ctx: Context) -> list[int]:
        self._live = [order_id for order_id in self._live if order_id in ctx.state.orders]
        return self._live

    def _place(self, ctx: Context, command: NewOrder) -> NewOrder:
        if command.order.type is OrderType.LIMIT and command.order.tif is TimeInForce.DAY:
            self._live.append(command.order.order_id)
        return command


class MarketMaker(Trader):
    def __init__(
        self,
        account_id: str,
        rate: float = 0.5,
        max_half_spread_ticks: int = 4,
        max_lots: int = 20,
        view_error_ticks: float = 1.0,
    ) -> None:
        super().__init__(account_id, rate)
        self.max_half_spread_ticks = max_half_spread_ticks
        self.max_lots = max_lots
        self.view_error_ticks = view_error_ticks

    def act(self, ctx: Context) -> list[Command]:
        commands: list[Command] = [CancelOrder(order_id) for order_id in self._still_resting(ctx)]
        self._live = []
        centre = ctx.fair + ctx.rng.gauss(0.0, self.view_error_ticks * ctx.tick)
        half = ctx.rng.randint(1, self.max_half_spread_ticks) * ctx.tick
        bid = ctx.round_down(centre - half)
        ask = ctx.round_up(centre + half)
        if ask <= bid:
            ask = min(bid + ctx.tick, ctx.instrument.band_high)
            bid = min(bid, ask - ctx.tick)
        lot = ctx.instrument.lot_size
        buy_size = ctx.rng.randint(1, self.max_lots) * lot
        sell_size = ctx.rng.randint(1, self.max_lots) * lot
        commands.append(self._place(ctx, ctx.order(self.account_id, Side.BUY, buy_size, bid)))
        commands.append(self._place(ctx, ctx.order(self.account_id, Side.SELL, sell_size, ask)))
        return commands


class NoiseTrader(Trader):
    def __init__(
        self,
        account_id: str,
        rate: float = 0.1,
        market_order_chance: float = 0.3,
        cancel_chance: float = 0.3,
        size_mu: float = 1.0,
        size_sigma: float = 1.0,
        max_lots: int = 200,
        stale_fraction: float = 0.0,
    ) -> None:
        super().__init__(account_id, rate)
        self.stale_fraction = stale_fraction  # 0 means never tidy up; otherwise drop orders this far from the price
        self.market_order_chance = market_order_chance
        self.cancel_chance = cancel_chance
        self.size_mu = size_mu
        self.size_sigma = size_sigma
        self.max_lots = max_lots

    def _size(self, ctx: Context) -> int:
        """Mostly small, occasionally very large (a log-normal has a heavy right tail)."""
        lots = int(ctx.rng.lognormal(self.size_mu, self.size_sigma))
        return min(max(lots, 1), self.max_lots) * ctx.instrument.lot_size

    def _stale(self, ctx: Context, resting: list[int]) -> list[int]:
        """This trader's resting orders that the price has walked away from. Nobody leaves a quote that far off."""
        if self.stale_fraction <= 0 or ctx.state.session is not Session.OPEN:
            return []
        anchor = ctx.reference()
        far: list[int] = []
        for order_id in resting:
            if abs(ctx.state.orders[order_id].price - anchor) > self.stale_fraction * anchor:
                far.append(order_id)
        return far

    def act(self, ctx: Context) -> list[Command]:
        commands: list[Command] = []
        resting = self._still_resting(ctx)
        stale = self._stale(ctx, resting)
        if stale:
            for order_id in stale:
                self._live.remove(order_id)
            return [CancelOrder(order_id) for order_id in stale]
        if resting and ctx.rng.chance(self.cancel_chance):
            victim = resting[ctx.rng.randint(0, len(resting) - 1)]
            commands.append(CancelOrder(victim))
            self._live.remove(victim)
            return commands
        side = Side.BUY if ctx.rng.chance(0.5) else Side.SELL
        quantity = self._size(ctx)
        session = ctx.state.session
        wants_market = ctx.rng.chance(self.market_order_chance)
        if session is Session.OPEN:
            opposite = ctx.state.best_ask() if side is Side.BUY else ctx.state.best_bid()
            if wants_market and opposite is not None:
                commands.append(ctx.order(self.account_id, side, quantity, None))
                return commands
        elif wants_market and ctx.rng.chance(0.2):
            commands.append(ctx.order(self.account_id, side, quantity, None))  # waits for the opening auction
            return commands
        # A limit order, usually behind the current price, sometimes across it.
        offset = ctx.rng.randint(-2, 6) * ctx.tick
        anchor = ctx.reference()
        price = ctx.round_down(anchor - offset) if side is Side.BUY else ctx.round_up(anchor + offset)
        commands.append(self._place(ctx, ctx.order(self.account_id, side, quantity, price)))
        return commands


class ValueTrader(Trader):
    def __init__(
        self,
        account_id: str,
        rate: float = 0.2,
        view_error_ticks: float = 3.0,
        threshold_ticks: int = 2,
        max_lots: int = 30,
    ) -> None:
        super().__init__(account_id, rate)
        self.view_error_ticks = view_error_ticks
        self.threshold_ticks = threshold_ticks
        self.max_lots = max_lots

    def act(self, ctx: Context) -> list[Command]:
        if ctx.state.session is not Session.OPEN:
            return []
        believed = ctx.fair + ctx.rng.gauss(0.0, self.view_error_ticks * ctx.tick)
        edge = self.threshold_ticks * ctx.tick
        ask, bid = ctx.state.best_ask(), ctx.state.best_bid()
        quantity = ctx.rng.randint(1, self.max_lots) * ctx.instrument.lot_size
        if ask is not None and believed - ask >= edge:
            return [ctx.order(self.account_id, Side.BUY, quantity, ctx.round_down(believed), TimeInForce.IOC)]
        if bid is not None and bid - believed >= edge:
            return [ctx.order(self.account_id, Side.SELL, quantity, ctx.round_up(believed), TimeInForce.IOC)]
        return []
