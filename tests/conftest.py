"""Test setup shared by every test.

Set MARKETLAB_TEST_PG to a PostgreSQL address (for example postgresql://postgres@127.0.0.1:5433/marketlab) and the
whole suite runs against PostgreSQL: every in-memory ledger becomes a fresh schema in that database. Without it
the tests use SQLite, as always. A few tests poke at SQLite itself (its PRAGMAs, its files) and are skipped then.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import pytest

PG_URL = os.environ.get("MARKETLAB_TEST_PG")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "sqlite_only: needs SQLite itself, skipped when the suite runs on PostgreSQL")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if PG_URL:
        skip = pytest.mark.skip(reason="this test is about SQLite itself")
        for item in items:
            if "sqlite_only" in item.keywords:
                item.add_marker(skip)


@pytest.fixture(autouse=True)
def _ledgers_on_postgres(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    if not PG_URL:
        yield
        return
    import psycopg

    from marketlab.ledger.ledger import Ledger

    original = Ledger.__init__
    setup = psycopg.connect(PG_URL, autocommit=True)  # one connection that makes the schemas

    def init(self: Any, path: str = ":memory:", **kwargs: Any) -> None:
        if path == ":memory:":
            schema = "t" + secrets.token_hex(6)
            setup.execute(f"CREATE SCHEMA {schema}")
            path = f"{PG_URL}{'&' if '?' in PG_URL else '?'}options={quote(f'-c search_path={schema}')}"
        original(self, path, **kwargs)

    monkeypatch.setattr(Ledger, "__init__", init)
    yield
    setup.close()
