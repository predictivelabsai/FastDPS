"""Portable SQLite/PostgreSQL transaction and migration layer."""
from __future__ import annotations

import atexit
import os
import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastdps.config import settings

try:
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
except ImportError:  # SQLite-only installations remain usable.
    ConnectionPool = None
    dict_row = None


MIGRATIONS = settings.root / "migrations"
_pools: dict[str, Any] = {}
_pool_lock = threading.Lock()


def _postgres_pool(url: str):
    if ConnectionPool is None:
        raise RuntimeError("PostgreSQL support requires psycopg[binary,pool]")
    pool = _pools.get(url)
    if pool is not None:
        return pool
    with _pool_lock:
        pool = _pools.get(url)
        if pool is None:
            pool = ConnectionPool(
                conninfo=url,
                min_size=int(os.getenv("DB_POOL_MIN_SIZE", "0")),
                max_size=int(os.getenv("DB_POOL_MAX_SIZE", "3")),
                timeout=10,
                kwargs={"row_factory": dict_row, "application_name": "fastdps"},
                check=ConnectionPool.check_connection,
                open=True,
            )
            _pools[url] = pool
    return pool


def close_pools() -> None:
    with _pool_lock:
        pools = list(_pools.values())
        _pools.clear()
    for pool in pools:
        pool.close()


atexit.register(close_pools)


class Transaction:
    def __init__(self, connection, dialect: str):
        self.connection = connection
        self.dialect = dialect

    def _sql(self, query: str) -> str:
        return query.replace("?", "%s") if self.dialect == "postgres" else query

    def execute(self, query: str, params: Sequence[Any] = ()):
        return self.connection.execute(self._sql(query), tuple(params))

    def one(self, query: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        row = self.execute(query, params).fetchone()
        return dict(row) if row else None

    def rows(self, query: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        return [dict(row) for row in self.execute(query, params).fetchall()]

    def scalar(self, query: str, params: Sequence[Any] = ()) -> Any:
        row = self.execute(query, params).fetchone()
        if row is None:
            return None
        if isinstance(row, sqlite3.Row):
            return row[0]
        return next(iter(row.values()))


class Database:
    def __init__(self, url: str = "", path: str | Path = "", schema: str = "fast_dps"):
        self.url = str(url).strip()
        self.path = Path(path or settings.sqlite_path)
        self.schema = schema
        self.dialect = "postgres" if self.url else "sqlite"

    @classmethod
    def from_env(cls) -> "Database":
        return cls(settings.database_url, settings.sqlite_path, settings.database_schema)

    def connect(self):
        if self.dialect == "sqlite":
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=20)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")
            return connection
        pool = _postgres_pool(self.url)
        connection = pool.getconn()
        try:
            connection.execute(f'SET search_path TO "{self.schema}", public')
        except Exception:
            pool.putconn(connection, close=True)
            raise
        return connection

    def _release(self, connection) -> None:
        if self.dialect == "postgres":
            _postgres_pool(self.url).putconn(connection)
        else:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[Transaction]:
        connection = self.connect()
        try:
            yield Transaction(connection, self.dialect)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            self._release(connection)

    def one(self, query: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        with self.transaction() as tx:
            return tx.one(query, params)

    def rows(self, query: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        with self.transaction() as tx:
            return tx.rows(query, params)

    def scalar(self, query: str, params: Sequence[Any] = ()) -> Any:
        with self.transaction() as tx:
            return tx.scalar(query, params)

    def migrate(self) -> list[str]:
        # The baseline schema intentionally uses the SQL subset shared by
        # SQLite and PostgreSQL. PostgreSQL-only follow-ups live separately.
        directories = [MIGRATIONS / "sqlite"]
        if self.dialect == "postgres":
            directories.append(MIGRATIONS / "postgres")
        connection = self.connect()
        applied: list[str] = []
        try:
            if self.dialect == "postgres":
                connection.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
                connection.execute(f'SET search_path TO "{self.schema}", public')
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS schema_migrations "
                    "(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
                )
                done = {row["version"] for row in connection.execute("SELECT version FROM schema_migrations")}
                paths = sorted(path for directory in directories for path in directory.glob("*.sql"))
                for path in paths:
                    if path.stem in done:
                        continue
                    connection.execute(path.read_text(encoding="utf-8"))
                    connection.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (path.stem,))
                    applied.append(path.stem)
            else:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS schema_migrations "
                    "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
                )
                done = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
                for path in sorted(directories[0].glob("*.sql")):
                    if path.stem in done:
                        continue
                    connection.executescript(path.read_text(encoding="utf-8"))
                    connection.execute(
                        "INSERT INTO schema_migrations(version,applied_at) VALUES (?,datetime('now'))",
                        (path.stem,),
                    )
                    applied.append(path.stem)
            connection.commit()
            return applied
        except Exception:
            connection.rollback()
            raise
        finally:
            self._release(connection)


_database: Database | None = None


def get_database() -> Database:
    global _database
    if _database is None:
        _database = Database.from_env()
    return _database


def set_database(database: Database | None) -> None:
    global _database
    _database = database
