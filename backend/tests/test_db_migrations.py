from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from app import db_models  # noqa: F401
from app.db import Base, make_engine
from app.migrate import BASELINE_REVISION, upgrade_to_head


def _file_engine(tmp_path):
    return make_engine(f"sqlite:///{tmp_path / 'test.db'}")


def test_file_sqlite_uses_wal_and_busy_timeout(tmp_path):
    engine = _file_engine(tmp_path)
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_fresh_database_migrates_to_the_current_models(tmp_path):
    engine = _file_engine(tmp_path)
    upgrade_to_head(engine)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert diff == [], f"migrations are out of sync with db_models: {diff}"
    assert version == BASELINE_REVISION


def test_upgrade_is_idempotent(tmp_path):
    engine = _file_engine(tmp_path)
    upgrade_to_head(engine)
    upgrade_to_head(engine)  # second start of the container: nothing to do


def test_pre_alembic_database_is_adopted_without_data_loss(tmp_path):
    engine = _file_engine(tmp_path)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        # What a database from before the in-place ALTERs looked like.
        conn.execute(text("ALTER TABLE groups DROP COLUMN description"))
        conn.execute(text("ALTER TABLE tokens DROP COLUMN created_at"))
        conn.execute(text("INSERT INTO groups (id, name) VALUES ('g1', 'Keep me')"))

    upgrade_to_head(engine)

    inspector = inspect(engine)
    assert "description" in {c["name"] for c in inspector.get_columns("groups")}
    assert "created_at" in {c["name"] for c in inspector.get_columns("tokens")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT name FROM groups WHERE id='g1'")).scalar() == "Keep me"
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == BASELINE_REVISION


def test_failed_migration_leaves_no_partial_schema(tmp_path):
    """SQLite DDL must be transactional so a crash mid-migration can be retried."""
    engine = _file_engine(tmp_path)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE half_built (id INTEGER)"))
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert "half_built" not in inspect(engine).get_table_names()


def test_adoption_creates_tables_an_old_version_never_had(tmp_path):
    engine = _file_engine(tmp_path)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE remembered_merchants"))
        conn.execute(text("DROP TABLE import_mappings"))
    upgrade_to_head(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"remembered_merchants", "import_mappings"} <= tables


def test_empty_alembic_version_table_is_treated_as_unstamped(tmp_path):
    engine = _file_engine(tmp_path)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
    upgrade_to_head(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == BASELINE_REVISION
