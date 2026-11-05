"""The statement is worked out from ledger transactions alone; these tests check it against everything else."""

from __future__ import annotations

import random
from datetime import date

from marketlab.core import Side
from marketlab.ledger import STARTING_CASH, Ledger, build_statement
from marketlab.session import PracticeSession
from marketlab.sim import SimConfig

DAY = date(2026, 11, 2)
CONFIG = SimConfig(seed=4, open_seconds=60, pre_open_seconds=5, noise_traders=6)


def make(plan: str = "flat20", config: SimConfig = CONFIG) -> PracticeSession:
    return PracticeSession(config, Ledger(), "you", plan=plan, trading_date=DAY)


def test_a_new_account_has_one_row_and_no_costs() -> None:
    statement = build_statement(make().ledger, "you")
    assert [r.kind for r in statement.rows] == ["start"]
    assert statement.money == STARTING_CASH == statement.starting_money
    assert statement.total_charges == 0 and statement.charges_basis_points == 0
    assert statement.check() == []


def test_a_round_trip_adds_up_to_what_the_charges_took() -> None:
    session = make()
    session.advance(20)
    session.place(Side.BUY, 5)
    session.place(Side.SELL, 5, limit_price=session.sim.instrument.band_low)  # rests until a buyer shows up
    for _ in range(40):
        if session.portfolio().locked == 0:
            break
        session.advance(1, pause_on_fill=False)
    assert session.portfolio().locked == 0  # the sale went through (fixed seed, so this is repeatable)
    statement = build_statement(session.ledger, "you")
    kinds = [r.kind for r in statement.rows]
    assert kinds[0] == "start" and "buy" in kinds and "sell" in kinds
    assert sum(r.shares_change for r in statement.trades) == 0  # bought 5 and sold 5, however many fills it took
    assert [qty for _, qty in statement.holdings] in ([], [0])
    result = statement.result({})  # nothing is held, so no prices are needed
    assert result["gain"] == statement.sold - statement.bought - statement.total_charges
    assert result["gain_before_charges"] == statement.sold - statement.bought
    assert statement.total_charges > 0  # the flat plan charges a fee on every order
    assert statement.money == session.portfolio().cash
    assert statement.check() == []


def test_holdings_are_valued_at_the_prices_given() -> None:
    session = make()
    session.advance(20)
    session.place(Side.BUY, 5)
    statement = build_statement(session.ledger, "you")
    symbol = session.sim.instrument.symbol
    assert statement.holdings == ((symbol, 5),)
    assert statement.worth({symbol: 0}) == statement.money
    assert statement.worth({symbol: 100}) == statement.money + 500


def test_money_set_aside_for_open_orders_does_not_change_the_statement() -> None:
    session = make()
    session.advance(20)
    low = session.sim.instrument.band_low
    order_id, _ = session.place(Side.BUY, 10, limit_price=low)
    resting = build_statement(session.ledger, "you")
    assert resting.money == STARTING_CASH and [r.kind for r in resting.rows] == ["start"]
    assert session.portfolio().reserved > 0
    session.cancel(order_id)
    assert build_statement(session.ledger, "you") == resting


def test_charges_by_line_match_the_system_accounts() -> None:
    session = make("flat20")
    session.advance(20)
    session.place(Side.BUY, 5)
    statement = build_statement(session.ledger, "you")
    for line, amount in statement.charges_by_line.items():
        assert session.ledger.balance(f"system:costs:{line}") == amount  # only one owner trades here


def test_starting_shares_show_as_a_grant_row() -> None:
    session = make()
    session.ledger.grant_shares("you", session.sim.instrument.symbol, 7)
    statement = build_statement(session.ledger, "you")
    assert [r.kind for r in statement.rows] == ["start", "grant"]
    assert statement.holdings == ((session.sim.instrument.symbol, 7),)


def test_other_owners_trades_stay_out_of_my_statement() -> None:
    session = make()
    session.ledger.open_account("someone-else")
    other = build_statement(session.ledger, "someone-else")
    assert other.money == STARTING_CASH and len(other.rows) == 1
    assert build_statement(session.ledger, "you").rows[0].memo == "Starting virtual money"


def test_the_statement_agrees_with_the_ledger_on_many_random_days() -> None:
    for seed in range(15):
        rng = random.Random(seed)
        session = make(config=SimConfig(seed=seed, open_seconds=60, pre_open_seconds=5, noise_traders=6))
        session.advance(10)
        for _ in range(12):
            if session.finished:
                break
            side = rng.choice([Side.BUY, Side.SELL])
            try:
                session.place(side, rng.randint(1, 20))
            except Exception:  # a refused order is fine; it must leave no trace in the statement
                pass
            session.advance(rng.uniform(1, 5), pause_on_fill=False)
        statement = build_statement(session.ledger, "you")
        assert statement.check() == [], seed
        folio = session.portfolio()
        assert statement.money == folio.cash + folio.reserved, seed
        assert dict(statement.holdings).get(session.sim.instrument.symbol, 0) == folio.shares + folio.locked, seed
        assert sum(r.money_change for r in statement.rows) == statement.money, seed
        assert session.ledger.verify() == []
