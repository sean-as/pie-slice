"""
Runs Alembic migrations in-process at startup (equivalent to
`alembic upgrade head`, but works without alembic.ini and against the same
engine/connection the app uses — including the in-memory DB tests run on).
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
import sqlalchemy as sa
from alembic.migration import MigrationContext
from sqlalchemy import Connection, Engine, inspect, text

from app import db_models  # noqa: F401  (registers tables on Base.metadata)
from app.db import Base
from app.db import engine as default_engine

BASELINE_REVISION = "0001"
# Tables the baseline creates. A pre-Alembic database may predate some of them
# (the CSV-import tables were added later and `create_all` used to fill them in).
BASELINE_TABLES = frozenset(
    {
        "users", "tokens", "groups", "members", "expenses", "expense_splits",
        "settlements", "import_mappings", "imported_transactions",
        "pending_imports", "pending_import_items", "remembered_merchants",
    }
)
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _config(connection: Connection) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.attributes["connection"] = connection
    return cfg


def _adopt_legacy_database(connection: Connection, cfg: Config) -> None:
    """
    Databases created before Alembic (`create_all` plus ad-hoc ALTERs) have the
    app's tables but no recorded revision. Fill in anything an old version never
    created, bring the two in-place-added columns up to date, then mark the
    database as being at the baseline so `upgrade` does not try to create
    tables that already exist.
    """
    tables = set(inspect(connection).get_table_names())
    if "users" not in tables:
        return  # an empty database: the baseline migration builds everything
    if MigrationContext.configure(connection).get_current_revision() is not None:
        return  # already managed by Alembic

    # Only valid while the models still equal the baseline; adoption exists for
    # databases that predate Alembic, which can only be at the baseline.
    missing = sorted(BASELINE_TABLES - tables)
    if missing:
        Base.metadata.create_all(connection, tables=[Base.metadata.tables[n] for n in missing])

    inspector = inspect(connection)  # fresh: the tables may have just been created
    dialect = connection.dialect
    if "description" not in {c["name"] for c in inspector.get_columns("groups")}:
        col = sa.String(1000).compile(dialect=dialect)
        connection.execute(text(f"ALTER TABLE groups ADD COLUMN description {col}"))
    if "created_at" not in {c["name"] for c in inspector.get_columns("tokens")}:
        col = sa.DateTime().compile(dialect=dialect)
        connection.execute(text(f"ALTER TABLE tokens ADD COLUMN created_at {col}"))
    command.stamp(cfg, BASELINE_REVISION)


def upgrade_to_head(target: Engine | None = None) -> None:
    with (target or default_engine).begin() as connection:
        cfg = _config(connection)
        _adopt_legacy_database(connection, cfg)
        command.upgrade(cfg, "head")
