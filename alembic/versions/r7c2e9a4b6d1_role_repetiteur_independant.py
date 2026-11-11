"""Ajoute le rôle répétiteur et les champs de vérification/profil."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "r7c2e9a4b6d1"
down_revision: Union[str, Sequence[str], None] = "p4a1d7c8e2f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Le type natif SQLAlchemy stocke les noms des membres Enum en majuscules.
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE roleutilisateur ADD VALUE IF NOT EXISTS 'REPETITEUR'")

    with op.batch_alter_table("utilisateur") as batch:
        batch.add_column(sa.Column(
            "statut_verification_repetiteur", sa.String(length=20),
            nullable=False, server_default="non_concerne",
        ))
        batch.add_column(sa.Column("demande_repetiteur_le", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("verification_repetiteur_le", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column(
            "verification_repetiteur_par_id", sa.Integer(),
            sa.ForeignKey("utilisateur.id"), nullable=True,
        ))
        batch.add_column(sa.Column("motif_refus_repetiteur", sa.String(), nullable=True))
        batch.add_column(sa.Column("matieres_repetiteur", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("niveaux_repetiteur", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("tarif_horaire_repetiteur_ariary", sa.Integer(), nullable=True))

    op.create_index(
        "ix_utilisateur_statut_verification_repetiteur",
        "utilisateur",
        ["statut_verification_repetiteur"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        raise NotImplementedError(
            "PostgreSQL ne permet pas de retirer une valeur d'un enum natif. "
            "La suppression du rôle REPETITEUR nécessite une migration manuelle."
        )
    op.drop_index("ix_utilisateur_statut_verification_repetiteur", table_name="utilisateur")
    with op.batch_alter_table("utilisateur") as batch:
        for nom in (
            "tarif_horaire_repetiteur_ariary",
            "niveaux_repetiteur",
            "matieres_repetiteur",
            "motif_refus_repetiteur",
            "verification_repetiteur_par_id",
            "verification_repetiteur_le",
            "demande_repetiteur_le",
            "statut_verification_repetiteur",
        ):
            batch.drop_column(nom)
