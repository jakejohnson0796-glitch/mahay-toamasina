"""Relier les quiz et sessions Tuteur à leur cours source.

Les colonnes sont nullable pour préserver les historiques créés avant cette
version et les interactions qui ne sont pas issues d'un document.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f0b1c2d3e4f"
down_revision: Union[str, None] = "bca6e2d8f143"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tentativequiz",
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("document.id"), nullable=True),
    )
    op.create_index(
        "ix_tentativequiz_document_id",
        "tentativequiz",
        ["document_id"],
    )
    op.add_column(
        "sessiontuteur",
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("document.id"), nullable=True),
    )
    op.create_index(
        "ix_sessiontuteur_document_id",
        "sessiontuteur",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_sessiontuteur_document_id", table_name="sessiontuteur")
    op.drop_column("sessiontuteur", "document_id")
    op.drop_index("ix_tentativequiz_document_id", table_name="tentativequiz")
    op.drop_column("tentativequiz", "document_id")
