"""The ledger on PostgreSQL when several servers share it. Needs MARKETLAB_TEST_PG; skipped without it."""

from __future__ import annotations

import os
import secrets
import threading
from collections.abc import Iterator
from urllib.parse import quote

import pytest

from marketlab.ledger import Entry, Ledger, LedgerError
from marketlab.ledger.names import MARKET_CASH, cash_account

PG_URL = os.environ.get("MARKETLAB_TEST_PG")
pytestmark = pytest.mark.skipif(not PG_URL, reason="needs PostgreSQL: set MARKETLAB_TEST_PG")


@pytest.fixture
def url() -> Iterator[str]:
    import psycopg

    assert PG_URL
    schema = "p" + secrets.token_hex(5)
    with psycopg.connect(PG_URL, autocommit=True) as setup:
        setup.execute(f"CREATE SCHEMA {schema}")
    yield f"{PG_URL}{'&' if '?' in PG_URL else '?'}options={quote(f'-c search_path={schema}')}"


def in_threads(jobs: list[object]) -> list[BaseException]:
    errors: list[BaseException] = []

    def wrap(job: object) -> None:
        try:
            job()  # type: ignore[operator]
        except BaseException as error:  # noqa: BLE001 - collected and checked by the test
            errors.append(error)

    threads = [threading.Thread(target=wrap, args=(job,)) for job in jobs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return errors


def test_several_servers_starting_together_set_up_one_database(url: str) -> None:
    ledgers: list[Ledger] = []
    errors = in_threads([lambda: ledgers.append(Ledger(url)) for _ in range(6)])
    assert errors == []
    assert len(ledgers) == 6
    assert ledgers[0].conn.execute("SELECT version FROM schema_version").fetchall() == [(4,)]
    assert ledgers[0].conn.execute("SELECT count(*) FROM accounts WHERE id = 'system:capital'").fetchone()[0] == 1


def test_a_database_from_a_newer_version_is_refused(url: str) -> None:
    ledger = Ledger(url)
    ledger.conn.execute("UPDATE schema_version SET version = 99")
    with pytest.raises(LedgerError, match="newer version"):
        Ledger(url)


def test_transactions_touching_the_same_accounts_in_opposite_orders_do_not_deadlock(url: str) -> None:
    first = Ledger(url)
    for name in ("hot:a", "hot:b"):
        first.ensure_account(name, "INR", allows_negative=True)

    def worker(n: int) -> None:
        mine = Ledger(url)
        for i in range(250):
            # half the threads list the two shared accounts one way round, half the other: without a fixed order
            # inside the ledger, two of them end up each holding what the other wants
            pair = [Entry("hot:a", 1), Entry("hot:b", -1)]
            mine.post(pair if n % 2 else pair[::-1], at=i, memo="shared", cause=f"t{n}-{i}")

    assert in_threads([lambda n=n: worker(n) for n in range(8)]) == []
    assert first.balance("hot:a") == 8 * 250 and first.balance("hot:b") == -8 * 250
    assert first.verify() == []


def test_two_servers_cannot_spend_the_same_money_at_the_same_moment(url: str) -> None:
    first = Ledger(url)
    first.open_account("shi", starting_cash=100)
    wins: list[int] = []
    refused: list[int] = []
    gate = threading.Barrier(2)

    def spend(n: int) -> None:
        mine = Ledger(url)
        gate.wait()
        try:
            mine.post([Entry(cash_account("shi"), -60), Entry(MARKET_CASH, 60)], at=0, memo="spend", cause=f"s{n}")
            wins.append(n)
        except LedgerError:
            refused.append(n)

    assert in_threads([lambda: spend(1), lambda: spend(2)]) == []
    assert len(wins) == 1 and len(refused) == 1  # one gets the money, the other is told no
    assert first.cash("shi") == 40
    assert first.verify() == []


def test_a_dropped_connection_is_reopened_between_transactions_and_fails_cleanly_inside_one(url: str) -> None:
    """A hosted database drops idle connections. Between transactions the ledger carries on; inside one it undoes it."""
    import psycopg

    assert PG_URL
    ledger = Ledger(url)
    ledger.ensure_account("a", "paise", allows_negative=True)
    ledger.ensure_account("b", "paise", allows_negative=True)

    def drop_every_other_connection() -> None:
        with psycopg.connect(PG_URL, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE pid <> pg_backend_pid() AND datname = current_database() AND application_name = ''"
            )

    drop_every_other_connection()
    assert ledger.balance("a") == 0  # a plain read finds the connection dead, reopens it, and answers

    with pytest.raises(psycopg.OperationalError):
        with ledger.batch():
            ledger.ensure_account("c", "paise")
            drop_every_other_connection()
            ledger.ensure_account("d", "paise")  # the transaction is gone with the connection
    assert ledger.balance("a") == 0  # the ledger is usable again straight away
    with pytest.raises(LedgerError):
        ledger.balance("c")  # and "c" was undone with the rest of the transaction
