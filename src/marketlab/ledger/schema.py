"""The database layout, as numbered migrations.

`PRAGMA user_version` records how many migrations a database file has had, so an old file is brought up to date
when it is opened and a file from a newer version of the program is refused instead of being corrupted.

The rules that matter most are enforced by the database itself, not only by Python:
- entries are append-only: nothing can be edited or deleted once written;
- an account that may not go negative cannot be pushed below zero, by any statement;
- an account's balance is updated by a trigger in the same statement as the entry, so it cannot drift.
That an entire transaction adds up to zero cannot be said in SQL, so the Python code checks it before writing and
`Ledger.verify()` checks it again afterwards.
"""

from __future__ import annotations

MIGRATIONS: list[str] = [
    """
    CREATE TABLE accounts (
        id TEXT PRIMARY KEY,
        unit TEXT NOT NULL,
        allows_negative INTEGER NOT NULL CHECK (allows_negative IN (0, 1)),
        balance INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        at_us INTEGER NOT NULL,
        memo TEXT NOT NULL,
        cause TEXT UNIQUE
    );

    CREATE TABLE entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id INTEGER NOT NULL REFERENCES transactions (id),
        account_id TEXT NOT NULL REFERENCES accounts (id),
        amount INTEGER NOT NULL CHECK (amount <> 0)
    );

    CREATE INDEX entries_by_account ON entries (account_id);
    CREATE INDEX entries_by_transaction ON entries (transaction_id);

    CREATE TRIGGER entries_update_balance AFTER INSERT ON entries
    BEGIN
        UPDATE accounts SET balance = balance + NEW.amount WHERE id = NEW.account_id;
    END;

    CREATE TRIGGER accounts_no_overdraft BEFORE UPDATE OF balance ON accounts
    WHEN NEW.balance < 0 AND NEW.allows_negative = 0
    BEGIN
        SELECT RAISE(ABORT, 'overdraft: this account cannot go below zero');
    END;

    CREATE TRIGGER entries_append_only_update BEFORE UPDATE ON entries
    BEGIN SELECT RAISE(ABORT, 'ledger entries cannot be changed'); END;
    CREATE TRIGGER entries_append_only_delete BEFORE DELETE ON entries
    BEGIN SELECT RAISE(ABORT, 'ledger entries cannot be deleted'); END;
    CREATE TRIGGER transactions_append_only_update BEFORE UPDATE ON transactions
    BEGIN SELECT RAISE(ABORT, 'ledger transactions cannot be changed'); END;
    CREATE TRIGGER transactions_append_only_delete BEFORE DELETE ON transactions
    BEGIN SELECT RAISE(ABORT, 'ledger transactions cannot be deleted'); END;
    """,
]
