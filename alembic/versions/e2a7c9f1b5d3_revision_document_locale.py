"""Store one shared document revision cache per selected language.

Revision ID: e2a7c9f1b5d3
Revises: d1e6f9a2b4c8
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2a7c9f1b5d3"
down_revision: Union[str, Sequence[str], None] = "d1e6f9a2b4c8"
branch_labels = None
depends_on = None


def _columns(bind) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(bind).get_columns("ficherevisiondocument")
    }


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("ficherevisiondocument"):
        return

    if "langue" not in _columns(bind):
        # All existing shared sheets were generated in French.
        op.add_column(
            "ficherevisiondocument",
            sa.Column("langue", sa.String(length=5), nullable=False, server_default="fr"),
        )

    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("ficherevisiondocument")}
    if "uq_ficherevisiondocument_document" in indexes:
        op.drop_index("uq_ficherevisiondocument_document", table_name="ficherevisiondocument")
    if "uq_ficherevisiondocument_document_langue" not in indexes:
        op.create_index(
            "uq_ficherevisiondocument_document_langue",
            "ficherevisiondocument",
            ["document_id", "langue"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("ficherevisiondocument"):
        return

    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("ficherevisiondocument")}
    if "uq_ficherevisiondocument_document_langue" in indexes:
        op.drop_index(
            "uq_ficherevisiondocument_document_langue",
            table_name="ficherevisiondocument",
        )

    if "langue" in _columns(bind):
        # A single-language schema cannot represent multiple locales. Keep the
        # French cache on downgrade, matching the legacy uniqueness rule.
        op.execute(sa.text("DELETE FROM ficherevisiondocument WHERE langue <> 'fr'"))
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("ficherevisiondocument", recreate="always") as batch:
                batch.drop_column("langue")
        else:
            op.drop_column("ficherevisiondocument", "langue")

    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("ficherevisiondocument")}
    if "uq_ficherevisiondocument_document" not in indexes:
        op.create_index(
            "uq_ficherevisiondocument_document",
            "ficherevisiondocument",
            ["document_id"],
            unique=True,
        )
