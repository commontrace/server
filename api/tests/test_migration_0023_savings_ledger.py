"""Migration 0023 chains the real head and creates/drops savings_ledger.

No DB: we (a) assert the revision chain, and (b) run upgrade()/downgrade()
against Alembic's OFFLINE SQL-emitting context (Postgres dialect, no
connection) and assert the emitted DDL touches the right table & columns.
"""

import importlib.util
import io
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations" / "versions" / "0023_savings_ledger.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m0023", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_revision_chain():
    mod = _load_migration()
    assert mod.revision == "230a1b2c3d4e"
    assert mod.down_revision == "220a1b2c3d4e"


def _emit(direction: str) -> str:
    """Run upgrade()/downgrade() in offline mode, capturing emitted SQL."""
    mod = _load_migration()
    buf = io.StringIO()

    ctx = MigrationContext.configure(
        dialect_name="postgresql",
        opts={
            "as_sql": True,
            "output_buffer": buf,
        },
    )
    ops = Operations(ctx)
    import alembic.op as alembic_op
    ops._install_proxy()
    try:
        getattr(mod, direction)()
    finally:
        ops._remove_proxy()
    return buf.getvalue().lower()


def test_upgrade_creates_table_and_columns():
    sql = _emit("upgrade")
    assert "create table" in sql
    assert "savings_ledger" in sql
    assert "minutes_saved" in sql
    assert "tokens_saved" in sql
    assert "event_type" in sql
    assert "created_at" in sql
    assert "ix_savings_ledger_created_at" in sql


def test_downgrade_drops_table_and_index():
    sql = _emit("downgrade")
    assert "drop" in sql
    assert "savings_ledger" in sql
