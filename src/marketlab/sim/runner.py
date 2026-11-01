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
from dataclasses import asdict, dataclass, fields
from typing import Any

from marketlab.codec import hash_events
from marketlab.core import Event, Exchange, Instrument, Session
from marketlab.projection import MarketState
from marketlab.sim.agents import Context, MarketMaker, NoiseTrader, Trader, ValueTrader
from marketlab.sim.processes import FairValue
from marketlab.sim.rng import SimRng

MICROS = 1_000_000


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


def build_traders(config: SimConfig) -> list[Trader]:
    traders: list[Trader] = []
    traders += [MarketMaker(f"MM{i + 1}") for i in range(config.market_makers)]
    traders += [NoiseTrader(f"NT{i + 1}") for i in range(config.noise_traders)]
    traders += [ValueTrader(f"VT{i + 1}") for i in range(config.value_traders)]
    return traders


def run_simulation(config: SimConfig) -> SimulationResult:
    instrument = config.instrument()
    rng = SimRng(config.seed)
    exchange = Exchange(instrument)
    state = MarketState(instrument)
    fair = FairValue(float(config.reference_price), config.volatility, config.jump_rate, config.jump_sd)
    traders = build_traders(config)
    events: list[Event] = []
    next_order_id = 0

    def new_id() -> int:
        nonlocal next_order_id
        next_order_id += 1
        return next_order_id

    ends: list[int] = []

    def record(new: list[Event]) -> None:
        events.extend(new)
        state.apply_all(new)
        if new:
            ends.append(len(events))

    open_at = config.pre_open_seconds * MICROS
    close_at = open_at + config.open_seconds * MICROS

    record(exchange.set_session(Session.PRE_OPEN, 0))

    # The queue holds (time, tie-break number, trader index). The tie-break keeps the order stable when two
    # wake-ups fall on the same microsecond.
    queue: list[tuple[int, int, int]] = []
    counter = 0
    for index, trader in enumerate(traders):
        counter += 1
        heapq.heappush(queue, (trader.delay(rng), counter, index))

    last_fair_time = 0
    opened = False
    while queue and queue[0][0] < close_at:
        when, _, index = heapq.heappop(queue)
        if not opened and when >= open_at:
            record(exchange.set_session(Session.OPEN, open_at))
            opened = True
        if opened and when < open_at:  # pragma: no cover - the heap is ordered, so this cannot happen
            raise AssertionError("time went backwards")
        fair.advance((when - last_fair_time) / MICROS, rng)
        last_fair_time = when
        trader = traders[index]
        context = Context(when, instrument, state, fair.value, rng, new_id)
        for command in trader.act(context):
            record(exchange.submit(command, when))
        counter += 1
        heapq.heappush(queue, (when + trader.delay(rng), counter, index))

    if not opened:
        record(exchange.set_session(Session.OPEN, open_at))
    if config.close_market:
        record(exchange.set_session(Session.CLOSED, close_at))

    return SimulationResult(config, instrument, events, hash_events(events), ends, exchange, state)
