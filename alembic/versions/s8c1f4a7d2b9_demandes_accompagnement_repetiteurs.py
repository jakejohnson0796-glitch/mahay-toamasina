"""Crée les demandes privées entre élèves et répétiteurs vérifiés."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "s8c1f4a7d2b9"
down_revision: Union[str, Sequence[str], None] = "r7c2e9a4b6d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demandeaccompagnement",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("etudiant_id", sa.Integer(), nullable=False),
        sa.Column("repetiteur_id", sa.Integer(), nullable=False),
        sa.Column("matiere", sa.String(length=120), nullable=False),
        sa.Column("niveau", sa.String(length=120), nullable=False),
        sa.Column("message", sa.String(length=800), nullable=False),
        sa.Column(
            "statut", sa.String(length=20),
            nullable=False, server_default="en_attente",
        ),
        sa.Column("date_creation", sa.DateTime(), nullable=False),
        sa.Column("date_traitement", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "etudiant_id <> repetiteur_id",
            name="ck_demandeaccompagnement_distinct",
        ),
        sa.CheckConstraint(
            "statut IN ('en_attente', 'acceptee', 'refusee')",
            name="ck_demandeaccompagnement_statut",
        ),
        sa.ForeignKeyConstraint(
            ["etudiant_id"], ["utilisateur.id"],
            name="fk_demandeaccompagnement_etudiant",
        ),
        sa.ForeignKeyConstraint(
            ["repetiteur_id"], ["utilisateur.id"],
            name="fk_demandeaccompagnement_repetiteur",
        ),
    )
    op.create_index(
        "ix_demandeaccompagnement_etudiant_id",
        "demandeaccompagnement", ["etudiant_id"],
    )
    op.create_index(
        "ix_demandeaccompagnement_repetiteur_id",
        "demandeaccompagnement", ["repetiteur_id"],
    )
    op.create_index(
        "ix_demandeaccompagnement_statut",
        "demandeaccompagnement", ["statut"],
    )
    op.create_index(
        "ix_demandeaccompagnement_repetiteur_statut",
        "demandeaccompagnement", ["repetiteur_id", "statut"],
    )
    op.create_index(
        "ix_demandeaccompagnement_etudiant_statut",
        "demandeaccompagnement", ["etudiant_id", "statut"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_demandeaccompagnement_etudiant_statut",
        table_name="demandeaccompagnement",
    )
    op.drop_index(
        "ix_demandeaccompagnement_repetiteur_statut",
        table_name="demandeaccompagnement",
    )
    op.drop_index(
        "ix_demandeaccompagnement_statut",
        table_name="demandeaccompagnement",
    )
    op.drop_index(
        "ix_demandeaccompagnement_repetiteur_id",
        table_name="demandeaccompagnement",
    )
    op.drop_index(
        "ix_demandeaccompagnement_etudiant_id",
        table_name="demandeaccompagnement",
    )
    op.drop_table("demandeaccompagnement")
