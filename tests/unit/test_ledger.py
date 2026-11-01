"""The ledger's rules, with small examples worked out by hand. Amounts are paise and shares."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from marketlab.ledger import (
    CAPITAL,
    COSTS,
    INR,
    MARKET_CASH,
    STARTING_CASH,
    Entry,
    InsufficientBalance,
    Ledger,
    LedgerError,
    Unbalanced,
    cash_account,
    shares_account,
)


@pytest.fixture
def ledger() -> Ledger:
    return Ledger()


def test_a_new_practice_account_gets_one_lakh_rupees(ledger: Ledger) -> None:
    ledger.open_account("shi")
    assert STARTING_CASH == 10_000_000  # 1,00,000 rupees is 10,000,000 paise
    assert ledger.cash("shi") == 10_000_000
    assert ledger.balance(CAPITAL) == -10_000_000  # the money came from somewhere, so the books still add up to zero
    assert ledger.verify() == []


def test_opening_twice_gives_the_money_only_once(ledger: Ledger) -> None:
    ledger.open_account("shi")
    ledger.open_account("shi")
    assert ledger.cash("shi") == 10_000_000
    assert len(ledger.transactions()) == 1


def test_a_trade_is_four_entries_that_balance_in_each_unit(ledger: Ledger) -> None:
    # Buy 10 shares at 2,500.00 rupees (250,000 paise): 2,500,000 paise leave the buyer's cash.
    ledger.open_account("shi")
    ledger.ensure_account(shares_account("shi", "DEMO1"), "DEMO1")
    ledger.ensure_account("system:market:shares:DEMO1", "DEMO1", allows_negative=True)
    ledger.post(
        [
            Entry(cash_account("shi"), -2_500_000),
            Entry(MARKET_CASH, 2_500_000),
            Entry(shares_account("shi", "DEMO1"), 10),
            Entry("system:market:shares:DEMO1", -10),
        ],
        at=5,
        memo="test buy",
    )
    assert ledger.cash("shi") == 7_500_000
    assert ledger.shares("shi", "DEMO1") == 10
    assert ledger.holdings("shi") == {"DEMO1": 10}
    assert ledger.verify() == []


def test_entries_that_do_not_add_up_are_refused_even_by_one_paisa(ledger: Ledger) -> None:
    ledger.open_account("shi")
    with pytest.raises(Unbalanced):
        ledger.post([Entry(cash_account("shi"), -100), Entry(MARKET_CASH, 99)], at=0, memo="off by one")
    assert ledger.cash("shi") == STARTING_CASH
    assert len(ledger.transactions()) == 1  # only the opening deposit


def test_money_cannot_pay_for_shares_by_itself(ledger: Ledger) -> None:
    # The two sides add up to zero if you ignore units, but money and shares are different things.
    ledger.open_account("shi")
    ledger.ensure_account(shares_account("shi", "DEMO1"), "DEMO1")
    with pytest.raises(Unbalanced):
        ledger.post([Entry(cash_account("shi"), -10), Entry(shares_account("shi", "DEMO1"), 10)], at=0, memo="bad")


def test_overdraft_is_refused_with_the_numbers_and_nothing_is_written(ledger: Ledger) -> None:
    ledger.open_account("shi", starting_cash=1_000)
    with pytest.raises(InsufficientBalance) as caught:
        ledger.post([Entry(cash_account("shi"), -1_001), Entry(MARKET_CASH, 1_001)], at=0, memo="too much")
    assert (caught.value.available, caught.value.needed, caught.value.unit) == (1_000, 1_001, INR)
    assert ledger.cash("shi") == 1_000
    assert ledger.balance(MARKET_CASH) == 0
    assert len(ledger.transactions()) == 1


def test_spending_exactly_everything_is_allowed(ledger: Ledger) -> None:
    ledger.open_account("shi", starting_cash=1_000)
    ledger.post([Entry(cash_account("shi"), -1_000), Entry(MARKET_CASH, 1_000)], at=0, memo="all of it")
    assert ledger.cash("shi") == 0


def test_a_transaction_is_judged_by_its_net_effect_on_each_account(ledger: Ledger) -> None:
    ledger.open_account("shi", starting_cash=100)
    ledger.post(
        [
            Entry(cash_account("shi"), -500),
            Entry(cash_account("shi"), 500),
            Entry(cash_account("shi"), -100),
            Entry(MARKET_CASH, 100),
        ],
        at=0,
        memo="in and out",
    )
    assert ledger.cash("shi") == 0
    assert all(len(t.entries) == len({e.account for e in t.entries}) for t in ledger.transactions())


@pytest.mark.parametrize("amount", [1.5, True, "5"])
def test_amounts_must_be_whole_numbers(ledger: Ledger, amount: object) -> None:
    ledger.open_account("shi")
    with pytest.raises(LedgerError):
        ledger.post([Entry(cash_account("shi"), amount), Entry(MARKET_CASH, 1)], at=0, memo="x")  # type: ignore[arg-type]


def test_empty_and_all_zero_transactions_and_unknown_accounts_are_refused(ledger: Ledger) -> None:
    ledger.open_account("shi")
    with pytest.raises(LedgerError):
        ledger.post([], at=0, memo="nothing")
    with pytest.raises(LedgerError):
        ledger.post([Entry(cash_account("shi"), 0), Entry(MARKET_CASH, 0)], at=0, memo="zeros")
    with pytest.raises(LedgerError):
        ledger.post([Entry("user:nobody:cash", 5), Entry(MARKET_CASH, -5)], at=0, memo="unknown")


def test_posting_the_same_cause_twice_does_nothing_the_second_time(ledger: Ledger) -> None:
    ledger.open_account("shi")
    entries = [Entry(cash_account("shi"), -10), Entry(MARKET_CASH, 10)]
    first = ledger.post(entries, at=0, memo="once", cause="run1:7:buy")
    second = ledger.post(entries, at=0, memo="once", cause="run1:7:buy")
    assert first is not None and second is None
    assert ledger.cash("shi") == STARTING_CASH - 10


def test_a_failed_batch_undoes_everything_in_it(ledger: Ledger) -> None:
    ledger.open_account("shi", starting_cash=100)
    with pytest.raises(InsufficientBalance), ledger.batch():
        ledger.post([Entry(cash_account("shi"), -60), Entry(MARKET_CASH, 60)], at=0, memo="fine")
        ledger.post([Entry(cash_account("shi"), -60), Entry(MARKET_CASH, 60)], at=0, memo="too much")
    assert ledger.cash("shi") == 100
    assert len(ledger.transactions()) == 1


def test_inside_a_batch_one_failure_can_be_caught_without_losing_the_rest(ledger: Ledger) -> None:
    ledger.open_account("shi", starting_cash=100)
    with ledger.batch():
        ledger.post([Entry(cash_account("shi"), -60), Entry(MARKET_CASH, 60)], at=0, memo="fine")
        with pytest.raises(InsufficientBalance):
            ledger.post([Entry(cash_account("shi"), -60), Entry(MARKET_CASH, 60)], at=0, memo="too much")
    assert ledger.cash("shi") == 40


# -- the database's own guards: what happens if someone bypasses the Python code ---------------------------------


def test_the_database_itself_refuses_an_overdraft(ledger: Ledger) -> None:
    ledger.open_account("shi", starting_cash=50)
    ledger.conn.execute("BEGIN")
    ledger.conn.execute("INSERT INTO transactions (at_us, memo) VALUES (0, 'raw')")
    with pytest.raises(sqlite3.IntegrityError, match="overdraft"):
        ledger.conn.execute(
            "INSERT INTO entries (transaction_id, account_id, amount) VALUES (last_insert_rowid(), ?, -51)",
            (cash_account("shi"),),
        )
    ledger.conn.execute("ROLLBACK")
    assert ledger.cash("shi") == 50


def test_entries_and_transactions_cannot_be_edited_or_deleted(ledger: Ledger) -> None:
    ledger.open_account("shi")
    for statement in (
        "UPDATE entries SET amount = 1",
        "DELETE FROM entries",
        "UPDATE transactions SET memo = 'changed'",
        "DELETE FROM transactions",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            ledger.conn.execute(statement)
    assert ledger.verify() == []


def test_verify_notices_a_balance_that_was_edited_by_hand(ledger: Ledger) -> None:
    ledger.open_account("shi")
    ledger.conn.execute("UPDATE accounts SET balance = balance + 1 WHERE id = ?", (cash_account("shi"),))
    problems = ledger.verify()
    assert len(problems) == 1 and "user:shi:cash" in problems[0]


def test_the_costs_account_exists_for_week_8(ledger: Ledger) -> None:
    assert ledger.balance(COSTS) == 0


# -- the file ----------------------------------------------------------------------------------------------------


def test_a_database_file_keeps_its_data_and_is_not_set_up_twice(tmp_path: Path) -> None:
    path = str(tmp_path / "practice.db")
    first = Ledger(path)
    first.open_account("shi")
    first.close()
    second = Ledger(path)
    assert second.cash("shi") == STARTING_CASH
    assert second.conn.execute("PRAGMA user_version").fetchone()[0] == 1
    second.open_account("shi")
    assert second.cash("shi") == STARTING_CASH
    second.close()


def test_a_database_from_a_newer_version_is_refused(tmp_path: Path) -> None:
    path = str(tmp_path / "future.db")
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA user_version = 99")
    raw.close()
    with pytest.raises(LedgerError, match="newer version"):
        Ledger(path)


def test_the_same_account_cannot_be_redefined(ledger: Ledger) -> None:
    ledger.ensure_account("user:a:cash", INR)
    ledger.ensure_account("user:a:cash", INR)  # same settings: fine
    with pytest.raises(LedgerError):
        ledger.ensure_account("user:a:cash", INR, allows_negative=True)
    with pytest.raises(LedgerError):
        ledger.ensure_account("user:a:cash", "DEMO1")
