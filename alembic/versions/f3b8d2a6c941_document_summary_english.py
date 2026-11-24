"""Persist English document summary and pedagogical-sheet cache.

Revision ID: f3b8d2a6c941
Revises: e2a7c9f1b5d3
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3b8d2a6c941"
down_revision: Union[str, Sequence[str], None] = "e2a7c9f1b5d3"
branch_labels = None
depends_on = None


def _columns(bind) -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(bind).get_columns("document")
    }


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("document"):
        return
    columns = _columns(bind)
    if "resume_ia_en" not in columns:
        op.add_column(
            "document",
            sa.Column("resume_ia_en", sa.Text(), nullable=False, server_default=""),
        )
    columns = _columns(bind)
    if "fiche_pedagogique_en_json" not in columns:
        op.add_column(
            "document",
            sa.Column("fiche_pedagogique_en_json", sa.Text(), nullable=False, server_default="{}"),
        )
    columns = _columns(bind)
    if "resume_statut_ia_en" not in columns:
        op.add_column(
            "document",
            sa.Column("resume_statut_ia_en", sa.String(length=24), nullable=False, server_default="a_generer"),
        )
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("document")}
    if "ix_document_resume_statut_ia_en" not in indexes:
        op.create_index(
            "ix_document_resume_statut_ia_en",
            "document",
            ["resume_statut_ia_en"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("document"):
        return
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("document")}
    if "ix_document_resume_statut_ia_en" in indexes:
        op.drop_index("ix_document_resume_statut_ia_en", table_name="document")
    columns = _columns(bind)
    if "resume_statut_ia_en" in columns:
        op.drop_column("document", "resume_statut_ia_en")
    columns = _columns(bind)
    if "fiche_pedagogique_en_json" in columns:
        op.drop_column("document", "fiche_pedagogique_en_json")
    columns = _columns(bind)
    if "resume_ia_en" in columns:
        op.drop_column("document", "resume_ia_en")
