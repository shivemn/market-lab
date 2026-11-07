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
    """
    -- one row per practice day that was played, so the history survives restarts; not part of the books
    CREATE TABLE days (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner TEXT NOT NULL,
        seed INTEGER NOT NULL,
        played_at TEXT NOT NULL DEFAULT (datetime('now')),
        finished INTEGER NOT NULL CHECK (finished IN (0, 1)),
        closes TEXT NOT NULL,
        summary TEXT NOT NULL
    );
    CREATE INDEX days_by_owner ON days (owner);
    """,
    """
    -- who may use an account name; not part of the books. A guest has no secret.
    CREATE TABLE users (
        key TEXT PRIMARY KEY,            -- the name in lower case, so 'Shi' and 'shi' are one person
        name TEXT NOT NULL,              -- the name as first typed; this is also the account's name in the books
        secret_hash TEXT,                -- scrypt hash, never the secret itself; NULL for a guest
        guest INTEGER NOT NULL DEFAULT 0 CHECK (guest IN (0, 1)),
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    -- a signed-in browser holds a token; only its hash is kept here
    CREATE TABLE logins (
        token_hash TEXT PRIMARY KEY,
        user_key TEXT NOT NULL REFERENCES users (key),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        expires_at TEXT NOT NULL
    );
    CREATE INDEX logins_by_user ON logins (user_key);
    """,
    """
    -- wrong guesses and new accounts, counted in the database so every server process sees the same count
    CREATE TABLE attempts (
        key TEXT NOT NULL,
        at REAL NOT NULL            -- seconds since 1970, from the clock of whichever server saw it
    );
    CREATE INDEX attempts_by_key ON attempts (key, at);
    """,
]


# The same layout for PostgreSQL. SQLite and PostgreSQL write triggers differently, so this is a second list that says
# the same things: the same tables, the same three database-enforced rules, the same order of migrations. All money and
# share amounts are BIGINT, because a balance in paise passes 2 billion at about 2 crore rupees. Dates are text in
# the same "YYYY-MM-DD HH:MM:SS" (UTC) form SQLite uses, so one set of Python code reads both.
_NOW_PG = "to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')"

MIGRATIONS_PG: list[str] = [
    """
    CREATE TABLE accounts (
        id TEXT PRIMARY KEY,
        unit TEXT NOT NULL,
        allows_negative SMALLINT NOT NULL CHECK (allows_negative IN (0, 1)),
        balance BIGINT NOT NULL DEFAULT 0
    );

    CREATE TABLE transactions (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        at_us BIGINT NOT NULL,
        memo TEXT NOT NULL,
        cause TEXT UNIQUE
    );

    CREATE TABLE entries (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        transaction_id BIGINT NOT NULL REFERENCES transactions (id),
        account_id TEXT NOT NULL REFERENCES accounts (id),
        amount BIGINT NOT NULL CHECK (amount <> 0)
    );

    CREATE INDEX entries_by_account ON entries (account_id);
    CREATE INDEX entries_by_transaction ON entries (transaction_id);

    -- ERRCODE 23514 (check violation) makes these arrive in Python as integrity errors, as they do in SQLite.
    CREATE FUNCTION entries_update_balance() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        UPDATE accounts SET balance = balance + NEW.amount WHERE id = NEW.account_id;
        RETURN NEW;
    END $$;
    CREATE TRIGGER entries_update_balance AFTER INSERT ON entries
        FOR EACH ROW EXECUTE FUNCTION entries_update_balance();

    CREATE FUNCTION accounts_no_overdraft() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.balance < 0 AND NEW.allows_negative = 0 THEN
            RAISE EXCEPTION 'overdraft: this account cannot go below zero' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER accounts_no_overdraft BEFORE UPDATE OF balance ON accounts
        FOR EACH ROW EXECUTE FUNCTION accounts_no_overdraft();

    CREATE FUNCTION ledger_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'ledger % cannot be %', TG_TABLE_NAME,
            CASE WHEN TG_OP = 'UPDATE' THEN 'changed' ELSE 'deleted' END USING ERRCODE = '23514';
    END $$;
    CREATE TRIGGER entries_append_only BEFORE UPDATE OR DELETE ON entries
        FOR EACH ROW EXECUTE FUNCTION ledger_append_only();
    CREATE TRIGGER transactions_append_only BEFORE UPDATE OR DELETE ON transactions
        FOR EACH ROW EXECUTE FUNCTION ledger_append_only();
    """,
    f"""
    CREATE TABLE days (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        owner TEXT NOT NULL,
        seed BIGINT NOT NULL,
        played_at TEXT NOT NULL DEFAULT ({_NOW_PG}),
        finished SMALLINT NOT NULL CHECK (finished IN (0, 1)),
        closes TEXT NOT NULL,
        summary TEXT NOT NULL
    );
    CREATE INDEX days_by_owner ON days (owner);
    """,
    f"""
    CREATE TABLE users (
        key TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        secret_hash TEXT,
        guest SMALLINT NOT NULL DEFAULT 0 CHECK (guest IN (0, 1)),
        created_at TEXT NOT NULL DEFAULT ({_NOW_PG})
    );
    CREATE TABLE logins (
        token_hash TEXT PRIMARY KEY,
        user_key TEXT NOT NULL REFERENCES users (key),
        created_at TEXT NOT NULL DEFAULT ({_NOW_PG}),
        expires_at TEXT NOT NULL
    );
    CREATE INDEX logins_by_user ON logins (user_key);
    """,
    """
    CREATE TABLE attempts (
        key TEXT NOT NULL,
        at DOUBLE PRECISION NOT NULL
    );
    CREATE INDEX attempts_by_key ON attempts (key, at);
    """,
]
