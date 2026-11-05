"""Twelve companies on one clock: the catalogue, shared moves, orders in each company, per-company results."""

from __future__ import annotations

import statistics
from datetime import date
from fractions import Fraction

import pytest

from marketlab.codec import hash_events
from marketlab.core import Side
from marketlab.ledger import STARTING_CASH, Ledger, OrderRefused, build_statement
from marketlab.world import CATALOGUE, SECTORS, PracticeWorld, World, WorldConfig

SMALL = WorldConfig(seed=3, pre_open_seconds=5, open_seconds=60)
DATE = date(2026, 11, 1)


def make(seed: int = 3, **extra: int) -> PracticeWorld:
    config = WorldConfig(seed=seed, pre_open_seconds=5, open_seconds=60, **extra)
    return PracticeWorld(config, Ledger(":memory:"), "you", trading_date=DATE)


def run_to_close(pw: PracticeWorld) -> None:
    while not pw.finished:
        pw.advance(10, pause_on_fill=False)


def test_the_catalogue_is_three_firms_in_each_of_four_sectors() -> None:
    assert len(CATALOGUE) == 12
    assert len({c.symbol for c in CATALOGUE}) == 12
    for key, _ in SECTORS:
        assert sum(1 for c in CATALOGUE if c.sector == key) == 3
    assert not any("DEMO" in c.symbol or "DEMO" in c.name.upper() for c in CATALOGUE)
    for c in CATALOGUE:
        assert c.price % 5 == 0  # a valid price on a 5 paise tick


def test_every_company_has_its_own_book_and_the_day_moves_together() -> None:
    world = World(SMALL)
    new, stopped = world.advance_to(10_000_000)
    assert not stopped and world.now == 10_000_000
    assert {sim.now for sim in world.sims.values()} == {10_000_000}
    assert all(len(events) > 0 for events in new.values())


def test_a_day_is_the_same_for_the_same_seed_and_different_for_another() -> None:
    def fingerprints(seed: int) -> dict[str, str]:
        world = World(WorldConfig(seed=seed, pre_open_seconds=5, open_seconds=30))
        world.advance_to(world.close_at)
        return world.fingerprints()

    assert fingerprints(4) == fingerprints(4)
    assert fingerprints(4) != fingerprints(5)


def test_it_does_not_matter_how_the_day_is_cut_into_steps() -> None:
    a, b = World(SMALL), World(SMALL)
    a.advance_to(a.close_at)
    for step in range(1, 66):
        b.advance_to(step * 1_000_000)
    assert a.fingerprints() == b.fingerprints()


def test_stocks_move_together_so_an_index_is_calmer_than_one_stock_but_not_flat() -> None:
    index_moves: list[float] = []
    stock_moves: list[float] = []
    for seed in range(1, 13):
        world = World(WorldConfig(seed=seed, pre_open_seconds=5, open_seconds=120))
        world.advance_to(world.close_at)
        prices, base = world.prices(), world.reference_prices()
        index = world.index("equal")
        index_moves.append(float(index.level(prices) / index.level(base) - 1))
        stock_moves += [prices[s] / base[s] - 1 for s in prices]
    index_sd = statistics.pstdev(index_moves)
    stock_sd = statistics.pstdev(stock_moves)
    assert index_sd < stock_sd  # diversification
    assert index_sd > 0.25 * stock_sd  # but the shared market move is still there (12 independent walks give ~0.29)


def test_orders_go_to_the_company_named_and_cash_is_shared() -> None:
    pw = make()
    pw.advance(10, pause_on_fill=False)
    pw.place("UDHAAR", Side.BUY, 5, limit_price=pw.world.prices()["UDHAAR"] - 1000)  # far below: it just waits
    pw.place("BHINDI", Side.BUY, 5, limit_price=pw.world.prices()["BHINDI"] - 1000)
    folio = pw.portfolio()
    assert folio.reserved > 0 and folio.cash + folio.reserved == STARTING_CASH
    assert {o.symbol for o in folio.open_orders} == {"UDHAAR", "BHINDI"}
    run_to_close(pw)
    folio = pw.portfolio()
    assert folio.reserved == 0 and not folio.open_orders  # everything ended with the day
    assert pw.ledger.verify() == []


def test_an_order_in_an_unknown_company_or_after_the_close_is_refused_and_changes_nothing() -> None:
    pw = make()
    before = pw.ledger.cash("you")
    with pytest.raises(OrderRefused, match="no company"):
        pw.place("NOSUCH", Side.BUY, 1)
    pw.advance(1, pause_on_fill=False)
    with pytest.raises(OrderRefused, match="available"):
        pw.place("KIRANA", Side.BUY, 100_000)
    assert pw.ledger.cash("you") == before
    run_to_close(pw)
    with pytest.raises(OrderRefused, match="closed"):
        pw.place("KIRANA", Side.BUY, 1)


def test_money_set_aside_in_one_company_cannot_be_spent_in_another() -> None:
    pw = make()
    pw.advance(6, pause_on_fill=False)  # after the opening auction would be later; before it, market orders wait
    pw.place("BUGFIX", Side.BUY, 20, limit_price=pw.world.prices()["BUGFIX"] - 400)  # about 20 x 4,125 = 82,500
    with pytest.raises(OrderRefused, match="available"):
        pw.place("KIRANA", Side.BUY, 10, limit_price=pw.world.prices()["KIRANA"] - 400)  # 10 x 3,900 = 39,000


def test_the_day_pauses_everywhere_when_one_of_your_orders_trades() -> None:
    pw = make()
    pw.advance(3, pause_on_fill=False)
    pw.place("PAKKA", Side.BUY, 1)  # a market order sent before the open waits for the opening auction
    result = pw.advance(40)
    assert result.stopped_for_fill and not result.finished
    assert {sim.now for sim in pw.world.sims.values()} == {pw.now}
    assert pw.portfolio().holdings["PAKKA"].shares == 1


def test_a_whole_day_with_orders_replays_to_the_same_fingerprints() -> None:
    pw = make(seed=9)
    pw.advance(10, pause_on_fill=False)
    pw.place("JUGAAD", Side.BUY, 3)
    pw.advance(20, pause_on_fill=False)
    pw.place("JUGAAD", Side.SELL, 2)
    pw.place("DAWAI", Side.BUY, 2)
    run_to_close(pw)
    replayed = pw.world.replay()
    assert {s: hash_events(sim.events) for s, sim in replayed.items()} == pw.fingerprints()


def test_profit_and_loss_per_company_adds_up_to_the_whole_account() -> None:
    pw = make(seed=11)
    pw.advance(10, pause_on_fill=False)
    for symbol in ("UDHAAR", "BUGFIX", "BIJLI"):
        pw.place(symbol, Side.BUY, 4)
    pw.advance(15, pause_on_fill=False)
    pw.place("UDHAAR", Side.SELL, 2)
    pw.place("BIJLI", Side.SELL, 4)
    pw.advance(30, pause_on_fill=False)
    positions = pw.positions()
    statement = build_statement(pw.ledger, "you")
    total_gain = statement.worth(pw.world.prices()) - statement.starting_money
    assert sum(p.net_exact for p in positions.values()) == total_gain  # exactly, with no rounding
    assert sum(p.charges for p in positions.values()) == statement.total_charges
    assert positions["BIJLI"].shares == 0 and positions["BIJLI"].unrealised == 0
    assert positions["UDHAAR"].shares == 2
    today = pw.today(positions)
    assert sum(today.values()) == pytest.approx(total_gain, abs=len(today))  # the first day: all of it is today


def test_average_cost_works_by_hand() -> None:
    pw = make(seed=2)
    ledger = pw.ledger
    pw.advance(8, pause_on_fill=False)
    # Put trades straight into the ledger as the gateway would, to check the method with round numbers.
    from marketlab.ledger import Entry, cash_account, market_shares_account, shares_account
    from marketlab.ledger.names import MARKET_CASH

    def trade(symbol: str, qty: int, price: int, buy: bool) -> None:
        value = qty * price
        sign = 1 if buy else -1
        ledger.post(
            [
                Entry(cash_account("you"), -sign * value),
                Entry(MARKET_CASH, sign * value),
                Entry(shares_account("you", symbol), sign * qty),
                Entry(market_shares_account(symbol), -sign * qty),
            ],
            at=1,
            memo="test",
        )

    trade("MACHLI", 10, 1000, True)  # 10 at 10.00
    trade("MACHLI", 10, 1200, True)  # 10 at 12.00: average 11.00
    trade("MACHLI", 5, 1500, False)  # sell 5 at 15.00: locks in (15 - 11) x 5 = 20.00
    position = pw.positions({"MACHLI": 1300})["MACHLI"]
    assert position.shares == 15 and position.average_cost == 1100
    assert position.realised == 2000
    assert position.unrealised == 15 * 1300 - 15 * 1100
    assert position.net_exact == Fraction(2000 + 3000)


def test_a_day_can_open_at_the_previous_close_and_the_index_carries_on() -> None:
    first = make(seed=3)
    run_to_close(first)
    closes = first.world.prices()
    level_at_close = first.world.index("cap").level(closes)
    second = PracticeWorld(SMALL, Ledger(":memory:"), "you", trading_date=DATE, previous_close=closes)
    assert second.world.reference_prices() == closes
    assert second.world.index("cap").level(second.world.prices()) == level_at_close  # not reset to 1000
    assert all(sim.instrument.reference_price == closes[s] for s, sim in second.world.sims.items())


def test_a_missing_previous_close_is_refused() -> None:
    with pytest.raises(ValueError, match="no previous close"):
        World(SMALL, previous_close={"BHINDI": 18_240})


def test_traders_pull_quotes_the_price_has_walked_away_from() -> None:
    """Without this, a stale order left from the opening gets hit later and draws a spike on the chart."""
    from marketlab.sim import SimConfig, Simulation

    config = SimConfig(seed=7, symbol="X", reference_price=400_000, noise_traders=8, value_traders=2, volatility=0.0003)

    def stalest(stale: float) -> float:
        sim = Simulation(config, None, stale)
        sim.advance_to(400 * 1_000_000)
        last = sim.state.last_price or config.reference_price
        mine = [o for o in sim.state.orders.values() if o.account_id.startswith("NT")]
        return max((abs(o.price - last) / last for o in mine), default=0.0)

    assert stalest(0.004) < stalest(0.0)
