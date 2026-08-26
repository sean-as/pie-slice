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
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./pieslice.db")

_connect_args: dict = {}
_engine_kwargs: dict = {}

if DATABASE_URL.startswith("sqlite"):
    # SQLite-specific tuning, isolated to this one branch — everything
    # downstream (models, store, routers) is unaware of which DB is active.
    _connect_args["check_same_thread"] = False
    if ":memory:" in DATABASE_URL:
        # An in-memory SQLite DB is per-connection; force one shared
        # connection for the engine's lifetime so all sessions see the
        # same data (used by tests).
        _engine_kwargs["poolclass"] = StaticPool

engine = create_engine(DATABASE_URL, connect_args=_connect_args, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass
