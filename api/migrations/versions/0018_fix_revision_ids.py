"""Fix duplicate revision IDs that caused alembic cycle

Revision ID: 180a0b0c0d0e
Revises: 170f6a1b2c3d
Create Date: 2026-04-06 07:00:00.000000

Migrations 0012-0017 had revision IDs that collided with 0000-0005
(same hex digits, just rotated). This caused a cycle error on
`alembic upgrade head`. The IDs were renamed to 120a-170f prefixed.

This migration updates the alembic_version row if it still holds
one of the old IDs, so production DBs that already ran the old
migrations transition cleanly to the new chain.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "180a0b0c0d0e"
down_revision: str = "170f6a1b2c3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Old ID -> New ID mapping
_OLD_TO_NEW = {
    "a1b2c3d4e5f6": "120a1b2c3d4e",  # but only if DB is at 0012+
    "b2c3d4e5f6a1": "130b2c3d4e5f",
    "c3d4e5f6a1b2": "140c3d4e5f6a",
    "d4e5f6a1b2c3": "150d4e5f6a1b",
    "e5f6a1b2c3d4": "160e5f6a1b2c",
    "f6a1b2c3d4e5": "170f6a1b2c3d",
}


def upgrade() -> None:
    # If the DB's alembic_version still has old 0017 ID, stamp it to new head.
    # This is a no-op if alembic already resolved to the new chain.
    for old_id, new_id in _OLD_TO_NEW.items():
        op.execute(
            f"UPDATE alembic_version SET version_num = '{new_id}' "
            f"WHERE version_num = '{old_id}'"
        )


def downgrade() -> None:
    pass
