"""Relier les quiz et sessions Tuteur à leur cours source.

Les colonnes restent nullable pour préserver les historiques existants et les
interactions qui ne sont pas issues d'un document. SQLite exige batch_alter_table
pour ajouter les clés étrangères à des tables existantes.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f0b1c2d3e4f"
down_revision: Union[str, None] = "bca6e2d8f143"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ajouter_lien_source(table: str) -> None:
    colonne = sa.Column("document_id", sa.Integer(), nullable=True)
    contrainte = f"fk_{table}_document_id_document"
    index = f"ix_{table}_document_id"
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table, recreate="always") as batch:
            batch.add_column(colonne)
            batch.create_foreign_key(
                contrainte,
                "document",
                ["document_id"],
                ["id"],
            )
            batch.create_index(index, ["document_id"])
        return

    op.add_column(table, colonne)
    op.create_foreign_key(
        contrainte,
        table,
        "document",
        ["document_id"],
        ["id"],
    )
    op.create_index(index, table, ["document_id"])


def _supprimer_lien_source(table: str) -> None:
    contrainte = f"fk_{table}_document_id_document"
    index = f"ix_{table}_document_id"
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table, recreate="always") as batch:
            batch.drop_index(index)
            batch.drop_constraint(contrainte, type_="foreignkey")
            batch.drop_column("document_id")
        return

    op.drop_index(index, table_name=table)
    op.drop_constraint(contrainte, table_name=table, type_="foreignkey")
    op.drop_column(table, "document_id")


def upgrade() -> None:
    _ajouter_lien_source("tentativequiz")
    _ajouter_lien_source("sessiontuteur")


def downgrade() -> None:
    _supprimer_lien_source("sessiontuteur")
    _supprimer_lien_source("tentativequiz")
