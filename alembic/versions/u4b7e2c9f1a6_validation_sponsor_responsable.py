"""Soumet les profils sponsor et responsable à validation administrateur."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "u4b7e2c9f1a6"
down_revision: Union[str, Sequence[str], None] = "t9d4f6a8c2e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("utilisateur") as batch:
        batch.add_column(sa.Column(
            "statut_verification_sponsor", sa.String(length=20),
            nullable=False, server_default="non_concerne",
        ))
        batch.add_column(sa.Column("demande_sponsor_le", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("verification_sponsor_le", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("verification_sponsor_par_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("motif_refus_sponsor", sa.String(), nullable=True))
        batch.add_column(sa.Column(
            "statut_verification_responsable", sa.String(length=20),
            nullable=False, server_default="non_concerne",
        ))
        batch.add_column(sa.Column("demande_responsable_le", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("verification_responsable_le", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("verification_responsable_par_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("motif_refus_responsable", sa.String(), nullable=True))
        batch.create_foreign_key(
            "fk_utilisateur_verification_sponsor_admin",
            "utilisateur",
            ["verification_sponsor_par_id"],
            ["id"],
        )
        batch.create_foreign_key(
            "fk_utilisateur_verification_responsable_admin",
            "utilisateur",
            ["verification_responsable_par_id"],
            ["id"],
        )

    op.create_index(
        "ix_utilisateur_statut_verification_sponsor",
        "utilisateur",
        ["statut_verification_sponsor"],
    )
    op.create_index(
        "ix_utilisateur_statut_verification_responsable",
        "utilisateur",
        ["statut_verification_responsable"],
    )

    # Les comptes sponsor/responsable déjà actifs avant cette règle sont
    # conservés tels quels (rétrocompatibilité) ; seuls les nouveaux profils
    # déposés à partir de cette version attendent explicitement l'admin.
    op.execute(
        "UPDATE utilisateur SET statut_verification_sponsor = 'approuve' "
        "WHERE role = 'SPONSOR' AND profil_souhaite = 'sponsor'"
    )
    op.execute(
        "UPDATE utilisateur SET statut_verification_responsable = 'approuve' "
        "WHERE role = 'RESPONSABLE' AND profil_souhaite = 'responsable'"
    )


def downgrade() -> None:
    op.drop_index("ix_utilisateur_statut_verification_responsable", table_name="utilisateur")
    op.drop_index("ix_utilisateur_statut_verification_sponsor", table_name="utilisateur")
    with op.batch_alter_table("utilisateur") as batch:
        batch.drop_constraint("fk_utilisateur_verification_responsable_admin", type_="foreignkey")
        batch.drop_constraint("fk_utilisateur_verification_sponsor_admin", type_="foreignkey")
        batch.drop_column("motif_refus_responsable")
        batch.drop_column("verification_responsable_par_id")
        batch.drop_column("verification_responsable_le")
        batch.drop_column("demande_responsable_le")
        batch.drop_column("statut_verification_responsable")
        batch.drop_column("motif_refus_sponsor")
        batch.drop_column("verification_sponsor_par_id")
        batch.drop_column("verification_sponsor_le")
        batch.drop_column("demande_sponsor_le")
        batch.drop_column("statut_verification_sponsor")
