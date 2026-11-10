"""Ajoute le choix de programme BEPC 2027 au profil scolaire de l'élève."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m1e7b3c5d9a2"
down_revision: Union[str, Sequence[str], None] = "l6d8b2f1a4c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "utilisateur",
        sa.Column("bepc_2027_parcours", sa.String(length=8), nullable=True),
    )
    op.create_index(
        "ix_utilisateur_bepc_2027_parcours",
        "utilisateur",
        ["bepc_2027_parcours"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_utilisateur_bepc_2027_parcours",
        table_name="utilisateur",
    )
    op.drop_column("utilisateur", "bepc_2027_parcours")
