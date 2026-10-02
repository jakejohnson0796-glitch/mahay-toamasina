"""Suivi de l'activite des utilisateurs et notification apres 3 jours d'absence."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a91c7e4d2b6f"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Cette migration peut arriver sur une base dont la colonne a déjà été
    # créée lors d'une tentative précédente. On ne doit jamais échouer sur
    # un "DuplicateColumn" dans ce cas.
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    colonnes = {col["name"] for col in inspector.get_columns("utilisateur")}
    if "derniere_activite_le" not in colonnes:
        op.add_column(
            "utilisateur",
            sa.Column("derniere_activite_le", sa.DateTime(), nullable=True),
        )

    index = {
        item["name"]
        for item in inspector.get_indexes("utilisateur")
        if item.get("name")
    }
    if "ix_utilisateur_derniere_activite_le" not in index:
        op.create_index(
            "ix_utilisateur_derniere_activite_le",
            "utilisateur",
            ["derniere_activite_le"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    index = {
        item["name"]
        for item in inspector.get_indexes("utilisateur")
        if item.get("name")
    }
    if "ix_utilisateur_derniere_activite_le" in index:
        op.drop_index(
            "ix_utilisateur_derniere_activite_le",
            table_name="utilisateur",
        )

    colonnes = {col["name"] for col in inspector.get_columns("utilisateur")}
    if "derniere_activite_le" in colonnes:
        op.drop_column("utilisateur", "derniere_activite_le")

    # PostgreSQL ne permet pas de supprimer directement une valeur d'un
    # enum natif. Le downgrade de cette migration retire la colonne/metadonnée
    # proprement ; la valeur d'enum restera inoffensive si des notifications
    # historiques l'ont utilisée.
