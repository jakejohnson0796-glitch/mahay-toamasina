"""Progression d'apprentissage par notion et contexte Tuteur IA.

Cette migration est volontairement idempotente : certaines bases de production
ont deja cree la table progressionnotion avant que la revision Alembic soit
enregistree. On complete alors le schema au lieu de tenter un CREATE TABLE
destructif ou de perdre les donnees existantes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8f4a1b7e2d9"
down_revision: Union[str, None] = "a91c7e4d2b6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _noms_colonnes(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def _noms_indexes(inspector, table: str) -> set[str]:
    return {
        index["name"]
        for index in inspector.get_indexes(table)
        if index.get("name")
    }


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ---------------------------------------------------------------
    # progressionnotion
    # ---------------------------------------------------------------
    if not inspector.has_table("progressionnotion"):
        op.create_table(
            "progressionnotion",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("utilisateur_id", sa.Integer(), nullable=False),
            sa.Column("matiere", sa.String(), nullable=False),
            sa.Column("notion", sa.String(), nullable=False),
            sa.Column("niveau", sa.String(), nullable=True),
            sa.Column(
                "nb_questions",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "nb_reussites",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "nb_erreurs",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column("derniere_erreur_le", sa.DateTime(), nullable=True),
            sa.Column("derniere_reussite_le", sa.DateTime(), nullable=True),
            sa.Column("date_maj", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["utilisateur_id"], ["utilisateur.id"]),
            sa.UniqueConstraint(
                "utilisateur_id",
                "matiere",
                "notion",
                name="uq_progression_notion_utilisateur_matiere_notion",
            ),
        )
    else:
        # La table existe deja : on ajoute uniquement les elements absents.
        # Les colonnes historiques ne sont jamais supprimees ni recreees.
        colonnes = _noms_colonnes(inspector, "progressionnotion")

        colonnes_manquantes = {
            "id": sa.Column("id", sa.Integer(), nullable=True),
            "utilisateur_id": sa.Column("utilisateur_id", sa.Integer(), nullable=True),
            "matiere": sa.Column("matiere", sa.String(), nullable=True),
            "notion": sa.Column("notion", sa.String(), nullable=True),
            "niveau": sa.Column("niveau", sa.String(), nullable=True),
            "nb_questions": sa.Column(
                "nb_questions",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            "nb_reussites": sa.Column(
                "nb_reussites",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            "nb_erreurs": sa.Column(
                "nb_erreurs",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            "derniere_erreur_le": sa.Column(
                "derniere_erreur_le",
                sa.DateTime(),
                nullable=True,
            ),
            "derniere_reussite_le": sa.Column(
                "derniere_reussite_le",
                sa.DateTime(),
                nullable=True,
            ),
            "date_maj": sa.Column(
                "date_maj",
                sa.DateTime(),
                nullable=True,
            ),
        }

        for nom, colonne in colonnes_manquantes.items():
            if nom not in colonnes:
                op.add_column("progressionnotion", colonne)

        inspector = sa.inspect(bind)

        uniques = inspector.get_unique_constraints("progressionnotion")
        unique_cible = ("utilisateur_id", "matiere", "notion")
        deja_unique = any(
            tuple(item.get("column_names") or ()) == unique_cible
            for item in uniques
        )
        if not deja_unique:
            op.create_unique_constraint(
                "uq_progression_notion_utilisateur_matiere_notion",
                "progressionnotion",
                ["utilisateur_id", "matiere", "notion"],
            )

    # ---------------------------------------------------------------
    # Index progressionnotion
    # ---------------------------------------------------------------
    inspector = sa.inspect(bind)
    indexes = _noms_indexes(inspector, "progressionnotion")

    index_cibles = {
        "ix_progressionnotion_utilisateur_id": ["utilisateur_id"],
        "ix_progressionnotion_matiere": ["matiere"],
        "ix_progressionnotion_notion": ["notion"],
        "ix_progression_notion_utilisateur_score": [
            "utilisateur_id",
            "nb_erreurs",
            "nb_reussites",
        ],
    }

    for nom_index, colonnes_index in index_cibles.items():
        if nom_index not in indexes:
            op.create_index(
                nom_index,
                "progressionnotion",
                colonnes_index,
            )

    # ---------------------------------------------------------------
    # sessiontuteur
    # ---------------------------------------------------------------
    inspector = sa.inspect(bind)
    if not inspector.has_table("sessiontuteur"):
        raise RuntimeError(
            "La table 'sessiontuteur' est absente alors que la migration "
            "c8f4a1b7e2d9 doit lui ajouter 'notion' et 'progression_id'."
        )

    colonnes_session = _noms_colonnes(inspector, "sessiontuteur")

    if "notion" not in colonnes_session:
        op.add_column(
            "sessiontuteur",
            sa.Column("notion", sa.String(), nullable=True),
        )

    if "progression_id" not in colonnes_session:
        op.add_column(
            "sessiontuteur",
            sa.Column("progression_id", sa.Integer(), nullable=True),
        )

    inspector = sa.inspect(bind)
    indexes_session = _noms_indexes(inspector, "sessiontuteur")
    if "ix_sessiontuteur_progression_id" not in indexes_session:
        op.create_index(
            "ix_sessiontuteur_progression_id",
            "sessiontuteur",
            ["progression_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("sessiontuteur"):
        indexes_session = _noms_indexes(inspector, "sessiontuteur")
        if "ix_sessiontuteur_progression_id" in indexes_session:
            op.drop_index(
                "ix_sessiontuteur_progression_id",
                table_name="sessiontuteur",
            )

        colonnes_session = _noms_colonnes(inspector, "sessiontuteur")
        if "progression_id" in colonnes_session:
            op.drop_column("sessiontuteur", "progression_id")
        if "notion" in colonnes_session:
            op.drop_column("sessiontuteur", "notion")

    inspector = sa.inspect(bind)
    if inspector.has_table("progressionnotion"):
        indexes = _noms_indexes(inspector, "progressionnotion")
        for nom_index in (
            "ix_progression_notion_utilisateur_score",
            "ix_progressionnotion_notion",
            "ix_progressionnotion_matiere",
            "ix_progressionnotion_utilisateur_id",
        ):
            if nom_index in indexes:
                op.drop_index(nom_index, table_name="progressionnotion")

        uniques = inspector.get_unique_constraints("progressionnotion")
        for unique in uniques:
            if unique.get("name") == "uq_progression_notion_utilisateur_matiere_notion":
                op.drop_constraint(
                    "uq_progression_notion_utilisateur_matiere_notion",
                    "progressionnotion",
                    type_="unique",
                )
                break

        op.drop_table("progressionnotion")
