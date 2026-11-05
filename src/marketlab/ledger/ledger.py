"""A double-entry ledger on SQLite.

Every change is a transaction made of entries. An entry adds an amount (positive or negative) to one account.
The entries of a transaction must add up to zero for each unit, so money (paise) and shares of each stock are
each conserved: nothing is created or lost, it only moves between accounts. Buying 10 shares for 25,000 paise
is four entries: the buyer's cash -25,000, the market's cash +25,000, the buyer's shares +10 and the market's
shares -10.

Practice accounts may not go below zero (no overdrafts, no short selling). System accounts may, because they
are the other side of everything.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

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
from marketlab.ledger.schema import MIGRATIONS

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


class Ledger:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, isolation_level=None)  # we begin and end transactions ourselves
        self._conn.execute("PRAGMA foreign_keys = ON")
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._depth = 0
        self._migrate()
        self.ensure_account(CAPITAL, INR, allows_negative=True)
        self.ensure_account(MARKET_CASH, INR, allows_negative=True)
        for line in COST_LINES:
            self.ensure_account(cost_account(line), INR)

    # -- the database file ------------------------------------------------------------------------------------

    @property
    def conn(self) -> sqlite3.Connection:
        """The raw connection. For tests that try to bypass the rules, and for reading."""
        return self._conn

    def close(self) -> None:
        self._conn.close()

    def _migrate(self) -> None:
        have = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        if have > len(MIGRATIONS):
            raise LedgerError(
                f"this database was made by a newer version (schema {have}, this program knows {len(MIGRATIONS)})"
            )
        for number in range(have, len(MIGRATIONS)):
            self._conn.executescript(f"BEGIN;\n{MIGRATIONS[number]}\nPRAGMA user_version = {number + 1};\nCOMMIT;")

    @contextmanager
    def batch(self) -> Iterator[None]:
        """Everything inside either happens or does not. Batches nest; a failure undoes only its own part."""
        outer = self._depth == 0
        name = f"batch{self._depth}"
        self._conn.execute("BEGIN IMMEDIATE" if outer else f"SAVEPOINT {name}")
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
        row = self._conn.execute("SELECT unit, allows_negative FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO accounts (id, unit, allows_negative) VALUES (?, ?, ?)",
                (account_id, unit, int(allows_negative)),
            )
        elif row[0] != unit or bool(row[1]) != allows_negative:
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
            cursor = self._conn.execute(
                "INSERT INTO transactions (at_us, memo, cause) VALUES (?, ?, ?)", (at, memo, cause)
            )
            transaction_id = cursor.lastrowid
            assert transaction_id is not None
            for entry in merged:
                try:
                    self._conn.execute(
                        "INSERT INTO entries (transaction_id, account_id, amount) VALUES (?, ?, ?)",
                        (transaction_id, entry.account, entry.amount),
                    )
                except sqlite3.IntegrityError as error:  # the database's own guard, if ours somehow missed it
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
