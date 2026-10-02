"""Score de maitrise et revision espacee par notion.

Migration rendue idempotente pour les bases ou une partie du schema a deja
ete creee avant l'enregistrement de la revision Alembic.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4b7c2d9f1a3"
down_revision: Union[str, None] = "c8f4a1b7e2d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _noms_colonnes(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("progressionnotion"):
        raise RuntimeError(
            "La table 'progressionnotion' est absente alors que la migration "
            "e4b7c2d9f1a3 doit lui ajouter les champs de maitrise."
        )

    colonnes = _noms_colonnes(inspector, "progressionnotion")

    a_ajouter = {
        "score_maitrise": sa.Column(
            "score_maitrise",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        "serie_reussites": sa.Column(
            "serie_reussites",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        "nb_revisions": sa.Column(
            "nb_revisions",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        "prochaine_revision_le": sa.Column(
            "prochaine_revision_le",
            sa.DateTime(),
            nullable=True,
        ),
    }

    for nom, colonne in a_ajouter.items():
        if nom not in colonnes:
            op.add_column("progressionnotion", colonne)

    # Reconstitue une premiere estimation a partir de l'historique deja
    # disponible. Le calcul est sans effet sur les autres colonnes.
    op.execute(
        sa.text(
            """
            UPDATE progressionnotion
            SET score_maitrise = CASE
                WHEN nb_questions > 0
                THEN CAST((nb_reussites * 100) / nb_questions AS INTEGER)
                ELSE 0
            END
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("progressionnotion"):
        return

    colonnes = _noms_colonnes(inspector, "progressionnotion")

    for nom in (
        "prochaine_revision_le",
        "nb_revisions",
        "serie_reussites",
        "score_maitrise",
    ):
        if nom in colonnes:
            op.drop_column("progressionnotion", nom)
