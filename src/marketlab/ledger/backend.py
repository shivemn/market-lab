"""Which database the ledger talks to: a SQLite file (the default) or a PostgreSQL server.

The ledger is written against a tiny common surface: ``execute(sql, params)`` returning something you can
``fetchone()``, ``fetchall()`` or loop over, with ``?`` for each value. SQLite already works that way. For
PostgreSQL this wrapper swaps ``?`` for ``%s`` and nothing else, so the SQL in the ledger stays one text.
"""

from __future__ import annotations

from typing import Any

POSTGRES_PREFIXES = ("postgresql://", "postgres://")


def is_postgres(path: str) -> bool:
    return path.startswith(POSTGRES_PREFIXES)


class PgConnection:
    """One PostgreSQL connection in autocommit mode: the ledger begins and ends its own transactions.

    Hosted databases drop idle connections (a free plan pauses its server after a few quiet minutes), and networks
    blink. When the connection is found dead between transactions, it is opened again and the statement is retried
    once. Inside a transaction it is not: the transaction died with the connection, so the error goes up and the
    ledger undoes the rest, exactly as for any other failure.
    """

    def __init__(self, url: str) -> None:
        try:
            import psycopg
        except ImportError as error:  # a clear message beats a stack trace
            raise RuntimeError('PostgreSQL support is not installed. Run:  pip install -e ".[postgres]"') from error
        self._url = url
        self._connect: Any = lambda: psycopg.connect(url, autocommit=True)
        self._conn: Any = self._connect()
        self._in_transaction = False
        self._lost: tuple[type[Exception], ...] = (psycopg.OperationalError, psycopg.InterfaceError)
        self.integrity_errors: tuple[type[Exception], ...] = (psycopg.IntegrityError,)
        self.retryable_errors: tuple[type[Exception], ...] = (psycopg.errors.DeadlockDetected,)

    def _track(self, sql: str) -> None:
        word = sql.lstrip()[:20].upper()
        if word.startswith("BEGIN"):
            self._in_transaction = True
        elif word.startswith("COMMIT") or (word.startswith("ROLLBACK") and not word.startswith("ROLLBACK TO")):
            self._in_transaction = False

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> Any:
        text = sql.replace("?", "%s")
        try:
            result = self._conn.execute(text, params)
        except self._lost:
            dead = self._conn.closed or self._conn.broken
            if self._in_transaction:
                # the transaction died with the connection. Give the ledger a live one for its rollback, and report it.
                self._in_transaction = False
                if dead:
                    self._reopen()
                raise
            if not dead:
                raise  # a real error on a healthy connection, not a dropped one
            self._reopen()
            result = self._conn.execute(text, params)
        self._track(sql)
        return result

    def _reopen(self) -> None:
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001 - it is already dead; all that matters is a fresh one
            pass
        self._conn = self._connect()

    def script(self, sql: str) -> None:
        """Run several statements at once. No values are passed, so `%` in the text means itself."""
        self._conn.execute(sql)

    def close(self) -> None:
        self._conn.close()
