"""
Engine/session setup — the only file that knows which database is
configured. `DATABASE_URL` selects the backend via SQLAlchemy's dialect
prefix in the connection string; nothing else in this app is SQLite- or
Postgres-specific, so switching later is a matter of:

  1. `pip install psycopg2-binary` (or another driver)
  2. DATABASE_URL=postgresql://user:pass@host/dbname

No code changes needed — this module never uses SQLite-only SQL, and all
column types (String/Integer/Date) are standard across backends.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./pieslice.db")


def make_engine(url: str) -> Engine:
    connect_args: dict = {}
    engine_kwargs: dict = {}
    is_sqlite = url.startswith("sqlite")
    in_memory = is_sqlite and ":memory:" in url

    if is_sqlite:
        # SQLite-specific tuning, isolated to this one branch — everything
        # downstream (models, store, routers) is unaware of which DB is active.
        connect_args["check_same_thread"] = False
        if in_memory:
            # An in-memory SQLite DB is per-connection; force one shared
            # connection for the engine's lifetime so all sessions see the
            # same data (used by tests).
            engine_kwargs["poolclass"] = StaticPool

    new_engine = create_engine(url, connect_args=connect_args, **engine_kwargs)

    if is_sqlite:

        @event.listens_for(new_engine, "connect")
        def _sqlite_connect(dbapi_connection, _record):  # noqa: ANN001
            # pysqlite only opens a transaction before DML, so DDL (migrations)
            # would autocommit and a failed migration would leave a half-built
            # schema. Take over transaction control and emit BEGIN ourselves
            # (see the "begin" listener below).
            dbapi_connection.isolation_level = None
            if not in_memory:
                cursor = dbapi_connection.cursor()
                # WAL: readers don't block the writer, and a crash can't
                # corrupt the main file. busy_timeout: wait for the lock
                # instead of failing instantly with "database is locked".
                # synchronous=NORMAL is the durable-enough pairing for WAL.
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()

        @event.listens_for(new_engine, "begin")
        def _sqlite_begin(connection):  # noqa: ANN001
            connection.exec_driver_sql("BEGIN")

    return new_engine


engine = make_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass
