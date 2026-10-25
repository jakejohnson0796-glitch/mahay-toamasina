"""Remove unique indexes duplicated by named UNIQUE constraints.

The UNIQUE constraints already own identical B-tree indexes. Keeping a second
unique index on each code column adds write/storage cost without adding query
coverage. The historical indexes are removed conditionally for compatibility
with databases created by different bootstrap paths.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e9c7a1b3f6"
down_revision: Union[str, None] = "c4e8a1d9b7f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_etablissementscolaire_code", "etablissementscolaire", "code"),
    ("ix_matierescolaire_code", "matierescolaire", "code"),
    ("ix_referentielscolaire_code", "referentielscolaire", "code"),
)


def upgrade() -> None:
    bind = op.get_bind()
    # The duplicate indexes were observed on Supabase/PostgreSQL. Historical
    # SQLite migrations/model metadata do not necessarily create them, and
    # SQLite has no separate "public" schema.
    if bind.dialect.name != "postgresql":
        return

    inspector = sa.inspect(bind)
    for index_name, table_name, _column in _INDEXES:
        existing = {
            item["name"]
            for item in inspector.get_indexes(table_name, schema="public")
        }
        if index_name in existing:
            op.drop_index(index_name, table_name=table_name, schema="public")
            # Refresh after DDL so a subsequent table inspection is accurate.
            inspector = sa.inspect(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    inspector = sa.inspect(bind)
    for index_name, table_name, column_name in reversed(_INDEXES):
        existing = {
            item["name"]
            for item in inspector.get_indexes(table_name, schema="public")
        }
        if index_name not in existing:
            op.create_index(
                index_name, table_name, [column_name], unique=True, schema="public"
            )
            inspector = sa.inspect(bind)
