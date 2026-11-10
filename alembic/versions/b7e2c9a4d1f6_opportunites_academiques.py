"""Create the academic opportunities catalogue."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e2c9a4d1f6"
down_revision: Union[str, Sequence[str], None] = "m1e7b3c5d9a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportuniteacademique",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("titre", sa.String(length=180), nullable=False),
        sa.Column("categorie", sa.String(length=30), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("niveau_cible", sa.String(length=80), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("date_limite", sa.Date(), nullable=True),
        sa.Column("source_nom", sa.String(length=180), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("statut", sa.String(length=16), nullable=False),
        sa.Column("cree_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("verifie_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.Column("verifiee_le", sa.DateTime(), nullable=True),
        sa.Column("date_creation", sa.DateTime(), nullable=False),
        sa.Column("date_modification", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "categorie IN ('bourse', 'concours', 'admission', 'stage', 'formation', 'evenement')",
            name="ck_opportunite_academique_categorie",
        ),
        sa.CheckConstraint(
            "statut IN ('brouillon', 'publiee', 'archivee')",
            name="ck_opportunite_academique_statut",
        ),
    )
    for column in ("titre", "categorie", "niveau_cible", "region", "date_limite", "statut", "cree_par_id", "verifie_par_id"):
        op.create_index(f"ix_opportuniteacademique_{column}", "opportuniteacademique", [column])
    op.create_index("ix_opportunite_statut_date_limite", "opportuniteacademique", ["statut", "date_limite"])


def downgrade() -> None:
    op.drop_index("ix_opportunite_statut_date_limite", table_name="opportuniteacademique")
    for column in ("titre", "categorie", "niveau_cible", "region", "date_limite", "statut", "cree_par_id", "verifie_par_id"):
        op.drop_index(f"ix_opportuniteacademique_{column}", table_name="opportuniteacademique")
    op.drop_table("opportuniteacademique")
