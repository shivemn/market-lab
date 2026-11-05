"""A practice session: your orders in a live simulated day."""

from __future__ import annotations

from datetime import date

import pytest

from marketlab.core import Side, TimeInForce, Trade
from marketlab.ledger import STARTING_CASH, Ledger, OrderRefused
from marketlab.session import PracticeSession, replay
from marketlab.sim import SimConfig, run_simulation

CONFIG = SimConfig(seed=4, open_seconds=60, pre_open_seconds=5, noise_traders=6)
DAY = date(2026, 11, 1)
MICROS = 1_000_000


def make(ledger: Ledger | None = None, config: SimConfig = CONFIG, plan: str = "zero") -> PracticeSession:
    return PracticeSession(config, ledger or Ledger(), "you", plan=plan, trading_date=DAY)


def test_a_new_session_gives_the_account_its_money_and_nothing_else() -> None:
    session = make()
    folio = session.portfolio()
    assert (folio.cash, folio.reserved, folio.shares, folio.locked, folio.open_orders) == (STARTING_CASH, 0, 0, 0, ())
    assert session.now == 0 and not session.finished


def test_a_market_buy_in_an_open_market_trades_and_costs_what_the_ledger_says() -> None:
    session = make()
    session.advance(20)
    order_id, events = session.place(Side.BUY, 5)
    folio = session.portfolio()
    assert folio.shares == 5 and folio.reserved == 0 and folio.open_orders == ()
    assert folio.cash < STARTING_CASH
    assert order_id >= 1_000_000_000  # a person's orders are numbered apart from the traders'
    assert session.ledger.verify() == []


def test_a_resting_limit_order_sets_money_aside_and_a_cancel_frees_it() -> None:
    session = make()
    session.advance(20)
    low = session.sim.instrument.band_low
    order_id, _ = session.place(Side.BUY, 10, limit_price=low)  # nobody will sell this low
    folio = session.portfolio()
    assert folio.reserved > 10 * low and folio.cash == STARTING_CASH - folio.reserved
    assert [o.order_id for o in folio.open_orders] == [order_id]
    session.cancel(order_id)
    assert session.portfolio().reserved == 0 and session.portfolio().cash == STARTING_CASH


def test_cancelling_an_order_that_is_not_open_is_refused() -> None:
    session = make()
    session.advance(20)
    with pytest.raises(OrderRefused, match="not open"):
        session.cancel(123)


def test_a_refused_order_changes_nothing_about_the_day() -> None:
    session = make()
    session.advance(20)
    with pytest.raises(OrderRefused):
        session.place(Side.BUY, 1_000_000, limit_price=session.sim.instrument.band_high)
    with pytest.raises(OrderRefused):
        session.place(Side.SELL, 1)  # holds nothing
    session.advance(10_000, pause_on_fill=False)
    assert session.finished
    assert session.fingerprint() == run_simulation(CONFIG).sha256  # the same day as if I had never tried


def test_day_orders_still_resting_at_the_close_are_returned() -> None:
    session = make()
    session.advance(20)
    session.place(Side.BUY, 10, limit_price=session.sim.instrument.band_low)
    session.advance(10_000, pause_on_fill=False)
    folio = session.portfolio()
    assert session.finished and (folio.reserved, folio.open_orders) == (0, ())
    assert folio.cash == STARTING_CASH


def test_nothing_can_be_placed_after_the_close() -> None:
    session = make()
    session.advance(10_000, pause_on_fill=False)
    with pytest.raises(OrderRefused, match="closed"):
        session.place(Side.BUY, 1)


def test_advance_pauses_just_after_the_moment_one_of_my_orders_trades() -> None:
    session = make(config=SimConfig(seed=5, open_seconds=60, pre_open_seconds=5, noise_traders=6))
    session.advance(20)
    tick = session.sim.instrument.tick_size
    ask = session.sim.state.best_ask()
    assert ask is not None
    session.place(Side.BUY, 3, limit_price=ask - 2 * tick)  # just under the market: rests until a seller comes
    pauses = []
    while not session.finished:
        result = session.advance(1.0)
        if result.stopped_for_fill:
            pauses.append(result)
    assert pauses, "the resting order should have traded at some point"
    for result in pauses:
        mine = [e for e in result.events if isinstance(e, Trade) and "you" in (e.buy_account_id, e.sell_account_id)]
        assert mine
        assert result.now == mine[-1].sim_time + 1  # the moment after the trade, so nothing else is skipped
    assert session.portfolio().shares > 0


def test_a_session_that_never_finished_does_not_trap_money() -> None:
    ledger = Ledger()
    first = make(ledger)
    first.advance(20)
    first.place(Side.BUY, 10, limit_price=first.sim.instrument.band_low)
    assert first.portfolio().cash < STARTING_CASH
    second = make(ledger)  # the first one is simply forgotten, as when a browser tab is closed
    assert second.portfolio().cash == STARTING_CASH and second.portfolio().reserved == 0
    assert ledger.verify() == []


def test_ending_early_returns_what_is_set_aside() -> None:
    session = make()
    session.advance(20)
    session.place(Side.BUY, 10, limit_price=session.sim.instrument.band_low)
    session.end_early()
    assert session.portfolio().cash == STARTING_CASH


def test_a_session_replays_exactly_from_its_seed_and_commands() -> None:
    session = make()
    session.advance(15)
    session.place(Side.BUY, 4)
    session.advance(7.5)
    low = session.sim.instrument.band_low
    oid, _ = session.place(Side.BUY, 6, limit_price=low, tif=TimeInForce.DAY)
    session.advance(11)
    session.cancel(oid)
    session.place(Side.SELL, 2)
    session.advance(10_000, pause_on_fill=False)
    again = replay(session)
    assert again.result().sha256 == session.fingerprint()
    assert len(again.events) == len(session.sim.events)
