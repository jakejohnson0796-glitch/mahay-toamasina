"""Journalise les actions admin effectuées dans un espace utilisateur."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "t9d4f6a8c2e1"
down_revision: Union[str, Sequence[str], None] = "s8c1f4a7d2b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "journalactionadmin",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("admin_id", sa.Integer(), nullable=False),
        sa.Column("utilisateur_cible_id", sa.Integer(), nullable=False),
        sa.Column("utilisateur_cible_nom", sa.String(length=120), nullable=False),
        sa.Column("methode", sa.String(length=10), nullable=False),
        sa.Column("chemin", sa.String(length=240), nullable=False),
        sa.Column("statut_http", sa.Integer(), nullable=False),
        sa.Column("date_creation", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_journalactionadmin_admin_id", "journalactionadmin", ["admin_id"])
    op.create_index("ix_journalactionadmin_utilisateur_cible_id", "journalactionadmin", ["utilisateur_cible_id"])
    op.create_index("ix_journalactionadmin_date_creation", "journalactionadmin", ["date_creation"])
    op.create_index("ix_journalactionadmin_admin_date", "journalactionadmin", ["admin_id", "date_creation"])
    op.create_index("ix_journalactionadmin_cible_date", "journalactionadmin", ["utilisateur_cible_id", "date_creation"])


def downgrade() -> None:
    op.drop_index("ix_journalactionadmin_cible_date", table_name="journalactionadmin")
    op.drop_index("ix_journalactionadmin_admin_date", table_name="journalactionadmin")
    op.drop_index("ix_journalactionadmin_date_creation", table_name="journalactionadmin")
    op.drop_index("ix_journalactionadmin_utilisateur_cible_id", table_name="journalactionadmin")
    op.drop_index("ix_journalactionadmin_admin_id", table_name="journalactionadmin")
    op.drop_table("journalactionadmin")
