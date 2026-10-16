"""Invalider les sessions quand une méthode MFA change.

Revision ID: d3f6a9c1e2b4
Revises: c8d1f6a4b9e2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3f6a9c1e2b4"
down_revision: Union[str, Sequence[str], None] = "c8d1f6a4b9e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    colonnes = {
        colonne["name"]
        for colonne in sa.inspect(op.get_bind()).get_columns("utilisateur")
    }
    if "mfa_session_generation" not in colonnes:
        op.add_column(
            "utilisateur",
            sa.Column("mfa_session_generation", sa.String(), nullable=True),
        )


def downgrade() -> None:
    colonnes = {
        colonne["name"]
        for colonne in sa.inspect(op.get_bind()).get_columns("utilisateur")
    }
    if "mfa_session_generation" in colonnes:
        op.drop_column("utilisateur", "mfa_session_generation")
