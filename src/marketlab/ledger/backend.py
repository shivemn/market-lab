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
    """One PostgreSQL connection in autocommit mode: the ledger begins and ends its own transactions."""

    def __init__(self, url: str) -> None:
        try:
            import psycopg
        except ImportError as error:  # a clear message beats a stack trace
            raise RuntimeError('PostgreSQL support is not installed. Run:  pip install -e ".[postgres]"') from error
        self._conn: Any = psycopg.connect(url, autocommit=True)
        self.integrity_errors: tuple[type[Exception], ...] = (psycopg.IntegrityError,)
        self.retryable_errors: tuple[type[Exception], ...] = (psycopg.errors.DeadlockDetected,)

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> Any:
        return self._conn.execute(sql.replace("?", "%s"), params)

    def script(self, sql: str) -> None:
        """Run several statements at once. No values are passed, so `%` in the text means itself."""
        self._conn.execute(sql)

    def close(self) -> None:
        self._conn.close()
