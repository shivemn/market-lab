"""The simulation loop.

Time is logical, in microseconds, and moves only by jumping to the next scheduled wake-up (a discrete-event
simulation). A day looks like this:

    t = 0                       the market moves to PRE_OPEN
    0 .. pre_open_seconds       traders place opening orders
    t = pre_open_seconds        the opening auction runs and the market is OPEN
    .. + open_seconds           continuous trading
    end                         the market is CLOSED (unless close_market is False) and DAY orders expire

Everything random comes from one seeded generator, so a `SimConfig` (which holds the seed) fully determines the
run. The settings are written into the log header, which is what lets `marketlab replay` re-run a log and check
that it comes out identical.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields, replace
from typing import Any

from marketlab.codec import hash_events
from marketlab.core import Command, Event, Exchange, Instrument, NewOrder, Order, Session
from marketlab.projection import MarketState
from marketlab.sim.agents import Context, MarketMaker, NoiseTrader, Trader, ValueTrader
from marketlab.sim.processes import FairValue
from marketlab.sim.rng import SimRng

MICROS = 1_000_000

CommonReturn = Callable[[int, int], float]


@dataclass(frozen=True)
class SimConfig:
    seed: int = 1
    symbol: str = "DEMO1"
    reference_price: int = 250_000  # paise
    tick_size: int = 5
    lot_size: int = 1
    band_pct: int = 10
    pre_open_seconds: int = 60
    open_seconds: int = 600
    market_makers: int = 2
    noise_traders: int = 20
    value_traders: int = 3
    volatility: float = 0.0003  # per square root of a second
    jump_rate: float = 0.0005  # jumps per second
    jump_sd: float = 0.004
    close_market: bool = True

    def instrument(self) -> Instrument:
        return Instrument(self.symbol, self.tick_size, self.lot_size, self.reference_price, self.band_pct)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> SimConfig:
        known = {field.name for field in fields(SimConfig)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown simulation settings: {sorted(unknown)}")
        return SimConfig(**data)


@dataclass(frozen=True)
class SimulationResult:
    config: SimConfig
    instrument: Instrument
    events: list[Event]
    sha256: str
    ends: list[int]  # event counts at which a command finishes (see projection.command_ends)
    exchange: Exchange  # the live exchange at the end, kept for checks
    state: MarketState  # the market rebuilt from the events alone


def build_traders(config: SimConfig, stale_fraction: float = 0.0) -> list[Trader]:
    traders: list[Trader] = []
    traders += [MarketMaker(f"MM{i + 1}") for i in range(config.market_makers)]
    traders += [NoiseTrader(f"NT{i + 1}", stale_fraction=stale_fraction) for i in range(config.noise_traders)]
    traders += [ValueTrader(f"VT{i + 1}") for i in range(config.value_traders)]
    return traders


USER_ORDER_ID_START = 1_000_000_000  # a person's orders count up from here, so they never disturb the traders' ids


class SimulationFinished(Exception):
    """The day is over; nothing more can happen."""


class Simulation:
    """A day that can be stepped forward and, in between, handed a person's commands.

    `run_simulation` is this class run straight to the end. The rule that keeps stepping honest is:

        at `now`, every trader wake-up strictly before `now` has happened, and none at or after it.

    So a command injected at `now` goes in before any trader acts in that same microsecond, and replaying a day is
    just "advance to the time of each command, inject it". Injecting a command draws no random numbers, so a day
    with no commands is identical to `run_simulation`'s (a test checks the fingerprints).
    """

    def __init__(self, config: SimConfig, common: CommonReturn | None = None, stale_fraction: float = 0.0) -> None:
        self._stale_fraction = stale_fraction  # see NoiseTrader: orders this far from the price get tidied away
        self.config = config
        self._common = common  # moves shared with other stocks: (from, to) microseconds -> log-return
        self.instrument = config.instrument()
        self.exchange = Exchange(self.instrument)
        self.state = MarketState(self.instrument)
        self.events: list[Event] = []
        self.ends: list[int] = []
        self.script: list[tuple[int, Command]] = []  # what a person sent, and when: enough to replay the day
        self.now = 0
        self.opened = False
        self.finished = False
        self._rng = SimRng(config.seed)
        self._fair = FairValue(float(config.reference_price), config.volatility, config.jump_rate, config.jump_sd)
        self._traders = build_traders(config, stale_fraction)
        self._next_order_id = 0
        self._next_user_order_id = USER_ORDER_ID_START
        self._open_at = config.pre_open_seconds * MICROS
        self._close_at = self._open_at + config.open_seconds * MICROS
        self._last_fair_time = 0
        self._record(self.exchange.set_session(Session.PRE_OPEN, 0))
        # The queue holds (time, tie-break number, trader index). The tie-break keeps the order stable when two
        # wake-ups fall on the same microsecond.
        self._queue: list[tuple[int, int, int]] = []
        self._counter = 0
        for index, trader in enumerate(self._traders):
            self._counter += 1
            heapq.heappush(self._queue, (trader.delay(self._rng), self._counter, index))

    @property
    def open_at(self) -> int:
        return self._open_at

    @property
    def close_at(self) -> int:
        return self._close_at

    def new_user_order_id(self) -> int:
        self._next_user_order_id += 1
        return self._next_user_order_id

    def _new_id(self) -> int:
        self._next_order_id += 1
        return self._next_order_id

    def _record(self, new: list[Event]) -> None:
        self.events.extend(new)
        self.state.apply_all(new)
        if new:
            self.ends.append(len(self.events))

    def _open(self) -> None:
        self._record(self.exchange.set_session(Session.OPEN, self._open_at))
        self.opened = True

    def _run_wakeups(self, before: int, stop: Callable[[list[Event]], bool] | None) -> int | None:
        """Let every trader wake-up earlier than `before` happen. If `stop` says so after a wake-up, finish that
        microsecond and report it, leaving later wake-ups alone."""
        stopped_at: int | None = None
        while self._queue and self._queue[0][0] < before and self._queue[0][0] < self._close_at:
            when, _, index = heapq.heappop(self._queue)
            first = len(self.events)
            shared = self._common(self._last_fair_time, when) if self._common is not None else 0.0
            self._fair.advance((when - self._last_fair_time) / MICROS, self._rng, shared)
            self._last_fair_time = when
            trader = self._traders[index]
            context = Context(when, self.instrument, self.state, self._fair.value, self._rng, self._new_id)
            for command in trader.act(context):
                self._record(self.exchange.submit(command, when))
            self._counter += 1
            heapq.heappush(self._queue, (when + trader.delay(self._rng), self._counter, index))
            if stop is not None and stop(self.events[first:]):
                stopped_at = when
            if stopped_at is not None and (not self._queue or self._queue[0][0] > stopped_at):
                return stopped_at
        return None

    def advance_to(self, until: int, stop: Callable[[list[Event]], bool] | None = None) -> list[Event]:
        """Move the day forward to `until` microseconds, or to just after the first wake-up that makes `stop` true.

        Returns the events that happened. The day cannot go backwards or past its close.
        """
        if self.finished:
            return []
        if until < self.now:
            raise ValueError(f"cannot go back in time: now is {self.now}, asked for {until}")
        until = min(until, self._close_at)
        first = len(self.events)
        stopped = self._run_wakeups(until if self.opened else min(until, self._open_at), stop)
        if stopped is None and not self.opened and until >= self._open_at:
            self._open()
            stopped = self._run_wakeups(until, stop)
        if stopped is None:
            self.now = until
        else:
            self.now = stopped + 1  # the whole microsecond has happened, so the next moment is the one after
            if not self.opened and self.now >= self._open_at:
                self._open()
        if self.now >= self._close_at:
            self._finish()
        return self.events[first:]

    def _finish(self) -> None:
        if self.finished:
            return
        if not self.opened:
            self._open()
        if self.config.close_market:
            self._record(self.exchange.set_session(Session.CLOSED, self._close_at))
        self.finished = True

    def inject(self, command: Command) -> list[Event]:
        """A person's command, sent at the current moment. It is remembered so the day can be replayed."""
        if self.finished:
            raise SimulationFinished("the day is over")
        remembered = replace(command.order) if isinstance(command, NewOrder) else command
        self.script.append((self.now, NewOrder(remembered) if isinstance(remembered, Order) else remembered))
        new = self.exchange.submit(command, self.now)
        self._record(new)
        return new

    def result(self) -> SimulationResult:
        return SimulationResult(
            self.config, self.instrument, self.events, hash_events(self.events), self.ends, self.exchange, self.state
        )


def run_simulation(config: SimConfig) -> SimulationResult:
    simulation = Simulation(config)
    simulation.advance_to(simulation.close_at)
    return simulation.result()


def replay_with_commands(
    config: SimConfig,
    script: list[tuple[int, Command]],
    common: CommonReturn | None = None,
    stale_fraction: float = 0.0,
) -> Simulation:
    """Re-run a day in which a person sent commands. The result is identical, event for event."""
    simulation = Simulation(config, common, stale_fraction)
    for when, command in script:
        simulation.advance_to(when)
        command_copy = NewOrder(replace(command.order)) if isinstance(command, NewOrder) else command
        simulation.inject(command_copy)
    simulation.advance_to(simulation.close_at)
    return simulation
