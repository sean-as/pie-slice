"""
Alembic environment. The database URL and metadata come from the app itself
(`app.db`), so `alembic` on the command line and the in-process upgrade run at
startup (`app.migrate`) always target the same database.
"""

from __future__ import annotations

from alembic import context

from app import db_models  # noqa: F401  (registers tables on Base.metadata)
from app.db import Base, engine

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    # app.migrate passes its own connection (needed for in-memory test DBs).
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
    else:
        with engine.connect() as conn:
            _run(conn)


def _run(connection) -> None:  # noqa: ANN001
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite can't ALTER most things in place; batch mode rebuilds the
        # table instead. Harmless on other databases.
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("Offline (SQL script) migrations are not supported.")
run_migrations_online()
