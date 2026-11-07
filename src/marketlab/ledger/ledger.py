"""A double-entry ledger on SQLite (or PostgreSQL).

Every change is a transaction made of entries. An entry adds an amount (positive or negative) to one account.
The entries of a transaction must add up to zero for each unit, so money (paise) and shares of each stock are
each conserved: nothing is created or lost, it only moves between accounts. Buying 10 shares for 25,000 paise
is four entries: the buyer's cash -25,000, the market's cash +25,000, the buyer's shares +10 and the market's
shares -10.

Practice accounts may not go below zero (no overdrafts, no short selling). System accounts may, because they
are the other side of everything.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from marketlab.ledger.backend import PgConnection, is_postgres
from marketlab.ledger.names import (
    CAPITAL,
    COST_LINES,
    INR,
    MARKET_CASH,
    capital_shares_account,
    cash_account,
    cost_account,
    shares_account,
)
from marketlab.ledger.schema import MIGRATIONS, MIGRATIONS_PG

STARTING_CASH = 10_000_000  # 1,00,000 rupees, in paise


class LedgerError(Exception):
    """Something was refused, and nothing was written."""


class Unbalanced(LedgerError):
    """The entries of a transaction did not add up to zero."""


class InsufficientBalance(LedgerError):
    def __init__(self, account: str, unit: str, available: int, needed: int) -> None:
        super().__init__(f"{account} has {available} {unit} but this needs {needed}")
        self.account = account
        self.unit = unit
        self.available = available
        self.needed = needed


@dataclass(frozen=True, slots=True)
class Entry:
    account: str
    amount: int  # whole paise or whole shares; positive adds to the account, negative takes away


@dataclass(frozen=True, slots=True)
class Transaction:
    id: int
    at: int  # logical time in microseconds
    memo: str
    cause: str | None
    entries: tuple[Entry, ...]


def _utc(plus_days: int = 0) -> str:
    """A UTC time as text in the form both databases store: 'YYYY-MM-DD HH:MM:SS' (sorts the same as time does)."""
    return (datetime.now(UTC) + timedelta(days=plus_days)).strftime("%Y-%m-%d %H:%M:%S")


_MIGRATION_LOCK = 727401  # PostgreSQL advisory lock, so several servers starting together migrate one at a time


class Ledger:
    """`path` is a SQLite file name, ":memory:", or a PostgreSQL address (postgresql://user:password@host/database)."""

    def __init__(self, path: str = ":memory:", *, shared_across_threads: bool = False) -> None:
        # A web server may use the ledger from several threads. Then the caller must take turns (hold a lock).
        self._conn: Any
        self.postgres = is_postgres(path)
        if self.postgres:
            pg = PgConnection(path)
            self._conn = pg
            self._integrity = pg.integrity_errors
        else:
            self._conn = sqlite3.connect(
                path, isolation_level=None, check_same_thread=not shared_across_threads
            )  # we begin and end transactions ourselves
            self._conn.execute("PRAGMA foreign_keys = ON")
            if path != ":memory:":
                self._conn.execute("PRAGMA journal_mode = WAL")
                self._conn.execute("PRAGMA busy_timeout = 5000")  # wait for another process's write, not fail
            self._integrity = (sqlite3.IntegrityError,)
        self._depth = 0
        self._migrate()
        self.ensure_account(CAPITAL, INR, allows_negative=True)
        self.ensure_account(MARKET_CASH, INR, allows_negative=True)
        for line in COST_LINES:
            self.ensure_account(cost_account(line), INR)

    # -- the database file ------------------------------------------------------------------------------------

    @property
    def conn(self) -> Any:
        """The raw connection. For tests that try to bypass the rules, and for reading."""
        return self._conn

    @property
    def integrity_errors(self) -> tuple[type[Exception], ...]:
        """What this database raises when one of its own rules (no overdraft, append-only) is broken."""
        return self._integrity

    def close(self) -> None:
        self._conn.close()

    def _migrate(self) -> None:
        if self.postgres:
            self._migrate_postgres()
            return
        have = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        if have > len(MIGRATIONS):
            raise LedgerError(
                f"this database was made by a newer version (schema {have}, this program knows {len(MIGRATIONS)})"
            )
        for number in range(have, len(MIGRATIONS)):
            self._conn.executescript(f"BEGIN;\n{MIGRATIONS[number]}\nPRAGMA user_version = {number + 1};\nCOMMIT;")

    def _migrate_postgres(self) -> None:
        self._conn.execute("SELECT pg_advisory_lock(?)", (_MIGRATION_LOCK,))
        try:
            self._conn.script("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = self._conn.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                self._conn.execute("INSERT INTO schema_version (version) VALUES (0)")
            have = 0 if row is None else int(row[0])
            if have > len(MIGRATIONS_PG):
                known = len(MIGRATIONS_PG)
                raise LedgerError(
                    f"this database was made by a newer version (schema {have}, this program knows {known})"
                )
            for number in range(have, len(MIGRATIONS_PG)):
                self._conn.script(
                    f"BEGIN;\n{MIGRATIONS_PG[number]}\nUPDATE schema_version SET version = {number + 1};\nCOMMIT;"
                )
        finally:
            self._conn.execute("SELECT pg_advisory_unlock(?)", (_MIGRATION_LOCK,))

    # -- the history of days played --------------------------------------------------------------------------

    def record_day(
        self, owner: str, seed: int, *, finished: bool, closes: dict[str, int], summary: dict[str, Any]
    ) -> int:
        """Remember one practice day: what it was, how it ended and every trade the person made."""
        row = self._conn.execute(
            "INSERT INTO days (owner, seed, finished, closes, summary) VALUES (?, ?, ?, ?, ?) RETURNING id",
            (owner, seed, int(finished), json.dumps(closes), json.dumps(summary)),
        ).fetchone()
        return int(row[0])

    def days(self, owner: str) -> list[dict[str, Any]]:
        """The days this person has played, newest first."""
        rows = self._conn.execute(
            "SELECT id, seed, played_at, finished, summary FROM days WHERE owner = ? ORDER BY id DESC", (owner,)
        ).fetchall()
        return [{"id": r[0], "seed": r[1], "played_at": r[2], "finished": bool(r[3]), **json.loads(r[4])} for r in rows]

    def last_closes(self, owner: str) -> dict[str, int] | None:
        """The closing prices of the last day this person played to the end, so the next day opens there."""
        row = self._conn.execute(
            "SELECT closes FROM days WHERE owner = ? AND finished = 1 ORDER BY id DESC LIMIT 1", (owner,)
        ).fetchone()
        return None if row is None else {k: int(v) for k, v in json.loads(row[0]).items()}

    # -- who may use an account name -------------------------------------------------------------------------

    def create_user(self, name: str, secret_hash: str | None, *, guest: bool = False) -> bool:
        """Add a user. False if the name (in any capitals) is already taken."""
        try:
            self._conn.execute(
                "INSERT INTO users (key, name, secret_hash, guest) VALUES (?, ?, ?, ?)",
                (name.lower(), name, secret_hash, int(guest)),
            )
        except self._integrity:
            return False
        return True

    def user(self, name: str) -> tuple[str, str | None, bool] | None:
        """(name as registered, secret hash, is a guest) for this name in any capitals, or None."""
        row = self._conn.execute("SELECT name, secret_hash, guest FROM users WHERE key = ?", (name.lower(),)).fetchone()
        return None if row is None else (str(row[0]), row[1], bool(row[2]))

    def add_login(self, token_hash: str, name: str, *, days: int) -> None:
        self._conn.execute(
            "INSERT INTO logins (token_hash, user_key, expires_at) VALUES (?, ?, ?)",
            (token_hash, name.lower(), _utc(days)),
        )

    def login_user(self, token_hash: str) -> tuple[str, bool] | None:
        """(name, is a guest) for a live token, or None if it is unknown or has expired."""
        row = self._conn.execute(
            "SELECT u.name, u.guest FROM logins l JOIN users u ON u.key = l.user_key"
            " WHERE l.token_hash = ? AND l.expires_at > ?",
            (token_hash, _utc()),
        ).fetchone()
        return None if row is None else (str(row[0]), bool(row[1]))

    def end_login(self, token_hash: str) -> None:
        self._conn.execute("DELETE FROM logins WHERE token_hash = ?", (token_hash,))

    def purge_logins(self) -> None:
        """Forget tokens that have expired, and counted attempts older than a day."""
        self._conn.execute("DELETE FROM logins WHERE expires_at <= ?", (_utc(),))
        self._conn.execute("DELETE FROM attempts WHERE at < ?", (time.time() - 86_400,))

    # -- counting attempts, for rate limits shared by every server process -----------------------------------

    def attempts_since(self, key: str, since: float) -> list[float]:
        rows = self._conn.execute(
            "SELECT at FROM attempts WHERE key = ? AND at > ? ORDER BY at", (key, since)
        ).fetchall()
        return [float(r[0]) for r in rows]

    def add_attempt(self, key: str, at: float) -> None:
        self._conn.execute("INSERT INTO attempts (key, at) VALUES (?, ?)", (key, at))

    def clear_attempts(self, key: str) -> None:
        self._conn.execute("DELETE FROM attempts WHERE key = ?", (key,))

    @contextmanager
    def batch(self) -> Iterator[None]:
        """Everything inside either happens or does not. Batches nest; a failure undoes only its own part."""
        outer = self._depth == 0
        name = f"batch{self._depth}"
        begin = "BEGIN" if self.postgres else "BEGIN IMMEDIATE"  # SQLite: take the write lock now, not half way in
        self._conn.execute(begin if outer else f"SAVEPOINT {name}")
        self._depth += 1
        try:
            yield
        except BaseException:
            self._depth -= 1
            if outer:
                self._conn.execute("ROLLBACK")
            else:
                self._conn.execute(f"ROLLBACK TO {name}")
                self._conn.execute(f"RELEASE {name}")
            raise
        self._depth -= 1
        self._conn.execute("COMMIT" if outer else f"RELEASE {name}")

    # -- accounts ---------------------------------------------------------------------------------------------

    def ensure_account(self, account_id: str, unit: str, *, allows_negative: bool = False) -> None:
        """Create the account if it is new. Asking again with different settings is an error, not a change."""
        # "do nothing if it exists" is what makes this safe when several servers start at the same moment
        self._conn.execute(
            "INSERT INTO accounts (id, unit, allows_negative) VALUES (?, ?, ?) ON CONFLICT (id) DO NOTHING",
            (account_id, unit, int(allows_negative)),
        )
        row = self._conn.execute("SELECT unit, allows_negative FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if row[0] != unit or bool(row[1]) != allows_negative:
            raise LedgerError(f"account {account_id} already exists with different settings")

    def grant_shares(self, owner: str, symbol: str, quantity: int) -> None:
        """Give an owner some shares to start with (for practice scenarios and tests)."""
        if quantity <= 0:
            raise LedgerError("a grant must be of at least one share")
        account = shares_account(owner, symbol)
        self.ensure_account(account, symbol)
        self.ensure_account(capital_shares_account(symbol), symbol, allows_negative=True)
        self.post(
            [Entry(capital_shares_account(symbol), -quantity), Entry(account, quantity)],
            at=0,
            memo=f"Starting shares of {symbol}",
        )

    def has_account(self, account_id: str) -> bool:
        return self._conn.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,)).fetchone() is not None

    def open_account(self, owner: str, starting_cash: int = STARTING_CASH, *, allows_negative: bool = False) -> None:
        """Open an owner's cash account and give it virtual money. Doing it twice gives the money only once."""
        if starting_cash < 0:
            raise LedgerError("starting cash cannot be negative")
        cash = cash_account(owner)
        self.ensure_account(cash, INR, allows_negative=allows_negative)
        if starting_cash > 0:
            self.post(
                [Entry(CAPITAL, -starting_cash), Entry(cash, starting_cash)],
                at=0,
                memo="Starting virtual money",
                cause=f"open:{owner}",
            )

    def balance(self, account_id: str) -> int:
        row = self._conn.execute("SELECT balance FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if row is None:
            raise LedgerError(f"no such account: {account_id}")
        return int(row[0])

    def cash(self, owner: str) -> int:
        return self.balance(cash_account(owner))

    def shares(self, owner: str, symbol: str) -> int:
        try:
            return self.balance(shares_account(owner, symbol))
        except LedgerError:
            return 0

    def holdings(self, owner: str) -> dict[str, int]:
        """Shares held by an owner, by symbol, leaving out stocks they hold none of."""
        prefix = shares_account(owner, "")
        rows = self._conn.execute(
            "SELECT unit, balance FROM accounts WHERE substr(id, 1, ?) = ? AND balance <> 0 ORDER BY unit",
            (len(prefix), prefix),
        ).fetchall()
        return {str(unit): int(balance) for unit, balance in rows}

    def balances(self) -> dict[str, int]:
        return {str(a): int(b) for a, b in self._conn.execute("SELECT id, balance FROM accounts ORDER BY id")}

    # -- posting ----------------------------------------------------------------------------------------------

    def post(self, entries: Sequence[Entry], *, at: int, memo: str, cause: str | None = None) -> int | None:
        """Write one balanced transaction. Returns its id, or None if this `cause` was already posted.

        `cause` is how replays stay safe: it names what the transaction records (for example one side of one
        trade in one run), so posting the same thing twice does nothing the second time.
        """
        merged = self._merge(entries)
        units = self._units(merged)
        totals: dict[str, int] = {}
        for entry in merged:
            totals[units[entry.account]] = totals.get(units[entry.account], 0) + entry.amount
        off = {unit: total for unit, total in totals.items() if total != 0}
        if off:
            raise Unbalanced(f"the entries do not add up to zero: {off}")

        with self.batch():
            if (
                cause is not None
                and self._conn.execute("SELECT 1 FROM transactions WHERE cause = ?", (cause,)).fetchone()
            ):
                return None
            self._check_overdrafts(merged, units)
            transaction_id = int(
                self._conn.execute(
                    "INSERT INTO transactions (at_us, memo, cause) VALUES (?, ?, ?) RETURNING id", (at, memo, cause)
                ).fetchone()[0]
            )
            # Several servers share one database and one set of system accounts (market cash, charges). If every
            # transaction touches accounts in the same order, they wait for each other instead of deadlocking.
            for entry in sorted(merged, key=lambda e: e.account) if self.postgres else merged:
                try:
                    self._conn.execute(
                        "INSERT INTO entries (transaction_id, account_id, amount) VALUES (?, ?, ?)",
                        (transaction_id, entry.account, entry.amount),
                    )
                except self._integrity as error:  # the database's own guard, if ours somehow missed it
                    raise LedgerError(str(error)) from error
            return transaction_id

    @staticmethod
    def _merge(entries: Sequence[Entry]) -> list[Entry]:
        """Add up repeated accounts and drop zeros, so a transaction is judged by what it does in the end."""
        sums: dict[str, int] = {}
        for entry in entries:
            if type(entry.amount) is not int:  # also rules out True/False and floats
                raise LedgerError(f"amounts must be whole numbers, got {entry.amount!r}")
            sums[entry.account] = sums.get(entry.account, 0) + entry.amount
        merged = [Entry(account, amount) for account, amount in sums.items() if amount != 0]
        if not merged:
            raise LedgerError("a transaction needs at least one entry that is not zero")
        return merged

    def _units(self, entries: Sequence[Entry]) -> dict[str, str]:
        units: dict[str, str] = {}
        for entry in entries:
            row = self._conn.execute("SELECT unit FROM accounts WHERE id = ?", (entry.account,)).fetchone()
            if row is None:
                raise LedgerError(f"no such account: {entry.account}")
            units[entry.account] = str(row[0])
        return units

    def _check_overdrafts(self, entries: Sequence[Entry], units: dict[str, str]) -> None:
        for entry in entries:
            if entry.amount >= 0:
                continue
            balance, allows_negative = self._conn.execute(
                "SELECT balance, allows_negative FROM accounts WHERE id = ?", (entry.account,)
            ).fetchone()
            if not allows_negative and balance + entry.amount < 0:
                raise InsufficientBalance(entry.account, units[entry.account], int(balance), -entry.amount)

    # -- reading and checking ---------------------------------------------------------------------------------

    def transactions(self) -> list[Transaction]:
        entries: dict[int, list[Entry]] = {}
        for transaction_id, account, amount in self._conn.execute(
            "SELECT transaction_id, account_id, amount FROM entries ORDER BY id"
        ):
            entries.setdefault(int(transaction_id), []).append(Entry(str(account), int(amount)))
        return [
            Transaction(
                int(i), int(at), str(memo), None if cause is None else str(cause), tuple(entries.get(int(i), []))
            )
            for i, at, memo, cause in self._conn.execute("SELECT id, at_us, memo, cause FROM transactions ORDER BY id")
        ]

    def verify(self) -> list[str]:
        """An audit that does not trust the stored balances. An empty list means the books are sound."""
        problems: list[str] = []
        for transaction_id, unit, total in self._conn.execute(
            """SELECT e.transaction_id, a.unit, SUM(e.amount) FROM entries e JOIN accounts a ON a.id = e.account_id
               GROUP BY e.transaction_id, a.unit HAVING SUM(e.amount) <> 0"""
        ):
            problems.append(f"transaction {transaction_id} is off by {total} {unit}")
        for account, stored, real in self._conn.execute(
            """SELECT a.id, a.balance, COALESCE(SUM(e.amount), 0) FROM accounts a
               LEFT JOIN entries e ON e.account_id = a.id
               GROUP BY a.id HAVING a.balance <> COALESCE(SUM(e.amount), 0)"""
        ):
            problems.append(f"account {account} stores {stored} but its entries add up to {real}")
        for (account,) in self._conn.execute("SELECT id FROM accounts WHERE balance < 0 AND allows_negative = 0"):
            problems.append(f"account {account} is below zero")
        return problems
