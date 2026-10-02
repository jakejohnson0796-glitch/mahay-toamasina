"""Memoire persistante des erreurs de l'ensemble IA."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8a2c6e4b1d9"
down_revision: Union[str, None] = "e4b7c2d9f1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _indexes(inspector, table: str) -> set[str]:
    return {i["name"] for i in inspector.get_indexes(table) if i.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("erreuriaensemble"):
        op.create_table(
            "erreuriaensemble",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("type_interaction", sa.String(), nullable=False),
            sa.Column("matiere", sa.String(), nullable=False, server_default=""),
            sa.Column("niveau", sa.String(), nullable=False, server_default=""),
            sa.Column("modele", sa.String(), nullable=False),
            sa.Column("categorie", sa.String(), nullable=False),
            sa.Column("signature", sa.String(), nullable=False),
            sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("premiere_detection_le", sa.DateTime(), nullable=False),
            sa.Column("derniere_detection_le", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "type_interaction",
                "matiere",
                "niveau",
                "modele",
                "categorie",
                "signature",
                name="uq_erreur_ia_ensemble_signature",
            ),
        )
    else:
        cols = {c["name"] for c in inspector.get_columns("erreuriaensemble")}
        for name, column in {
            "id": sa.Column("id", sa.Integer(), nullable=True),
            "type_interaction": sa.Column("type_interaction", sa.String(), nullable=True),
            "matiere": sa.Column("matiere", sa.String(), nullable=True, server_default=""),
            "niveau": sa.Column("niveau", sa.String(), nullable=True, server_default=""),
            "modele": sa.Column("modele", sa.String(), nullable=True),
            "categorie": sa.Column("categorie", sa.String(), nullable=True),
            "signature": sa.Column("signature", sa.String(), nullable=True),
            "occurrences": sa.Column("occurrences", sa.Integer(), nullable=True, server_default="1"),
            "premiere_detection_le": sa.Column("premiere_detection_le", sa.DateTime(), nullable=True),
            "derniere_detection_le": sa.Column("derniere_detection_le", sa.DateTime(), nullable=True),
        }.items():
            if name not in cols:
                op.add_column("erreuriaensemble", column)

        inspector = sa.inspect(bind)
        unique_cols = (
            "type_interaction", "matiere", "niveau", "modele", "categorie", "signature"
        )
        uniques = inspector.get_unique_constraints("erreuriaensemble")
        if not any(tuple(u.get("column_names") or ()) == unique_cols for u in uniques):
            op.create_unique_constraint(
                "uq_erreur_ia_ensemble_signature",
                "erreuriaensemble",
                list(unique_cols),
            )

    inspector = sa.inspect(bind)
    targets = {
        "ix_erreuriaensemble_type_interaction": ["type_interaction"],
        "ix_erreuriaensemble_matiere": ["matiere"],
        "ix_erreuriaensemble_niveau": ["niveau"],
        "ix_erreuriaensemble_modele": ["modele"],
        "ix_erreuriaensemble_categorie": ["categorie"],
        "ix_erreuriaensemble_signature": ["signature"],
        "ix_erreur_ia_ensemble_recurrence": [
            "type_interaction", "matiere", "niveau", "occurrences"
        ],
    }
    indexes = _indexes(inspector, "erreuriaensemble")
    for name, cols in targets.items():
        if name not in indexes:
            op.create_index(name, "erreuriaensemble", cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("erreuriaensemble"):
        return
    indexes = _indexes(inspector, "erreuriaensemble")
    for name in (
        "ix_erreur_ia_ensemble_recurrence",
        "ix_erreuriaensemble_signature",
        "ix_erreuriaensemble_categorie",
        "ix_erreuriaensemble_modele",
        "ix_erreuriaensemble_niveau",
        "ix_erreuriaensemble_matiere",
        "ix_erreuriaensemble_type_interaction",
    ):
        if name in indexes:
            op.drop_index(name, table_name="erreuriaensemble")
    op.drop_table("erreuriaensemble")
