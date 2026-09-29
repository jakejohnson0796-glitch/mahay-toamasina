"""Memoire persistante des erreurs de l'ensemble IA."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8a2c6e4b1d9"
down_revision: Union[str, None] = "e4b7c2d9f1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
    op.create_index(
        "ix_erreuriaensemble_type_interaction",
        "erreuriaensemble",
        ["type_interaction"],
    )
    op.create_index(
        "ix_erreuriaensemble_matiere",
        "erreuriaensemble",
        ["matiere"],
    )
    op.create_index(
        "ix_erreuriaensemble_niveau",
        "erreuriaensemble",
        ["niveau"],
    )
    op.create_index(
        "ix_erreuriaensemble_modele",
        "erreuriaensemble",
        ["modele"],
    )
    op.create_index(
        "ix_erreuriaensemble_categorie",
        "erreuriaensemble",
        ["categorie"],
    )
    op.create_index(
        "ix_erreuriaensemble_signature",
        "erreuriaensemble",
        ["signature"],
    )
    op.create_index(
        "ix_erreur_ia_ensemble_recurrence",
        "erreuriaensemble",
        ["type_interaction", "matiere", "niveau", "occurrences"],
    )


def downgrade() -> None:
    op.drop_index("ix_erreur_ia_ensemble_recurrence", table_name="erreuriaensemble")
    op.drop_index("ix_erreuriaensemble_signature", table_name="erreuriaensemble")
    op.drop_index("ix_erreuriaensemble_categorie", table_name="erreuriaensemble")
    op.drop_index("ix_erreuriaensemble_modele", table_name="erreuriaensemble")
    op.drop_index("ix_erreuriaensemble_niveau", table_name="erreuriaensemble")
    op.drop_index("ix_erreuriaensemble_matiere", table_name="erreuriaensemble")
    op.drop_index("ix_erreuriaensemble_type_interaction", table_name="erreuriaensemble")
    op.drop_table("erreuriaensemble")
