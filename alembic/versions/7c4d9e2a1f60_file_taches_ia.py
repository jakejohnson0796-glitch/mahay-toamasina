"""File durable pour les traitements IA hors chemin HTTP."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c4d9e2a1f60"
down_revision: Union[str, None] = "f8a2c6e4b1d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tacheia",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("type_tache", sa.String(), nullable=False),
        sa.Column("tentative_quiz_id", sa.Integer(), nullable=False),
        sa.Column("statut", sa.String(), nullable=False),
        sa.Column("nombre_essais", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("disponible_le", sa.DateTime(), nullable=False),
        sa.Column("prise_en_charge_le", sa.DateTime(), nullable=True),
        sa.Column("terminee_le", sa.DateTime(), nullable=True),
        sa.Column("derniere_erreur", sa.String(), nullable=True),
        sa.Column("date_creation", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tentative_quiz_id"],
            ["tentativequiz.id"],
        ),
        sa.UniqueConstraint(
            "type_tache",
            "tentative_quiz_id",
            name="uq_tache_ia_type_tentative",
        ),
    )
    op.create_index(
        "ix_tacheia_type_tache",
        "tacheia",
        ["type_tache"],
    )
    op.create_index(
        "ix_tacheia_tentative_quiz_id",
        "tacheia",
        ["tentative_quiz_id"],
    )
    op.create_index(
        "ix_tacheia_statut",
        "tacheia",
        ["statut"],
    )
    op.create_index(
        "ix_tacheia_disponible_le",
        "tacheia",
        ["disponible_le"],
    )
    op.create_index(
        "ix_tacheia_date_creation",
        "tacheia",
        ["date_creation"],
    )
    op.create_index(
        "ix_tache_ia_file",
        "tacheia",
        ["statut", "disponible_le", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tache_ia_file", table_name="tacheia")
    op.drop_index("ix_tacheia_date_creation", table_name="tacheia")
    op.drop_index("ix_tacheia_disponible_le", table_name="tacheia")
    op.drop_index("ix_tacheia_statut", table_name="tacheia")
    op.drop_index("ix_tacheia_tentative_quiz_id", table_name="tacheia")
    op.drop_index("ix_tacheia_type_tache", table_name="tacheia")
    op.drop_table("tacheia")
