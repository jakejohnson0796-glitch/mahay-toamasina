"""Metriques et routage adaptatif de l'ensemble IA."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9e5b7c1a2d40"
down_revision: Union[str, None] = "7c4d9e2a1f60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tacheia",
        sa.Column("strategie_verification", sa.String(), nullable=False, server_default="standard"),
    )
    op.add_column(
        "tacheia",
        sa.Column("score_risque", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_tacheia_strategie_verification",
        "tacheia",
        ["strategie_verification"],
    )

    op.create_table(
        "performancemodeleia",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("type_interaction", sa.String(), nullable=False),
        sa.Column("matiere", sa.String(), nullable=False, server_default=""),
        sa.Column("niveau", sa.String(), nullable=False, server_default=""),
        sa.Column("modele", sa.String(), nullable=False),
        sa.Column("strategie", sa.String(), nullable=False, server_default="standard"),
        sa.Column("appels", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confiants", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("problemes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("arbitrages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("derniere_duree_secondes", sa.Float(), nullable=True),
        sa.Column("duree_moyenne_secondes", sa.Float(), nullable=False, server_default="0"),
        sa.Column("premiere_utilisation_le", sa.DateTime(), nullable=False),
        sa.Column("derniere_utilisation_le", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "type_interaction",
            "matiere",
            "niveau",
            "modele",
            "strategie",
            name="uq_performance_modele_ia",
        ),
    )
    op.create_index(
        "ix_performancemodeleia_type_interaction",
        "performancemodeleia",
        ["type_interaction"],
    )
    op.create_index(
        "ix_performancemodeleia_matiere",
        "performancemodeleia",
        ["matiere"],
    )
    op.create_index(
        "ix_performancemodeleia_niveau",
        "performancemodeleia",
        ["niveau"],
    )
    op.create_index(
        "ix_performancemodeleia_modele",
        "performancemodeleia",
        ["modele"],
    )
    op.create_index(
        "ix_performancemodeleia_strategie",
        "performancemodeleia",
        ["strategie"],
    )
    op.create_index(
        "ix_performance_modele_ia_lookup",
        "performancemodeleia",
        ["type_interaction", "matiere", "niveau"],
    )


def downgrade() -> None:
    op.drop_index("ix_performance_modele_ia_lookup", table_name="performancemodeleia")
    op.drop_index("ix_performancemodeleia_strategie", table_name="performancemodeleia")
    op.drop_index("ix_performancemodeleia_modele", table_name="performancemodeleia")
    op.drop_index("ix_performancemodeleia_niveau", table_name="performancemodeleia")
    op.drop_index("ix_performancemodeleia_matiere", table_name="performancemodeleia")
    op.drop_index("ix_performancemodeleia_type_interaction", table_name="performancemodeleia")
    op.drop_table("performancemodeleia")

    op.drop_index("ix_tacheia_strategie_verification", table_name="tacheia")
    op.drop_column("tacheia", "score_risque")
    op.drop_column("tacheia", "strategie_verification")
