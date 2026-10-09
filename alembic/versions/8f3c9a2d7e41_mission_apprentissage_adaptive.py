"""Persiste l'étape de la mission adaptative par étudiant."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8f3c9a2d7e41"
down_revision: Union[str, None] = "d4e7f1a9c3b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "missionapprentissage",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("utilisateur_id", sa.Integer(), nullable=False),
        sa.Column("progression_id", sa.Integer(), nullable=False),
        sa.Column("etape", sa.String(), nullable=False, server_default="comprendre"),
        sa.Column("statut", sa.String(), nullable=False, server_default="active"),
        sa.Column("nb_tentatives", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dernier_score", sa.Integer(), nullable=True),
        sa.Column("derniere_tentative_id", sa.Integer(), nullable=True),
        sa.Column("derniere_session_tuteur_id", sa.Integer(), nullable=True),
        sa.Column("dernier_feedback", sa.String(), nullable=True),
        sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("date_maj", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("date_fin", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["utilisateur_id"], ["utilisateur.id"]),
        sa.ForeignKeyConstraint(["progression_id"], ["progressionnotion.id"]),
        sa.ForeignKeyConstraint(["derniere_tentative_id"], ["tentativequiz.id"]),
        sa.ForeignKeyConstraint(["derniere_session_tuteur_id"], ["sessiontuteur.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("utilisateur_id", name="uq_missionapprentissage_utilisateur"),
    )
    op.create_index("ix_missionapprentissage_utilisateur_id", "missionapprentissage", ["utilisateur_id"])
    op.create_index("ix_missionapprentissage_progression_id", "missionapprentissage", ["progression_id"])
    op.create_index("ix_missionapprentissage_etape", "missionapprentissage", ["etape"])
    op.create_index("ix_missionapprentissage_statut", "missionapprentissage", ["statut"])
    op.create_index("ix_missionapprentissage_derniere_tentative_id", "missionapprentissage", ["derniere_tentative_id"])
    op.create_index("ix_missionapprentissage_derniere_session_tuteur_id", "missionapprentissage", ["derniere_session_tuteur_id"])


def downgrade() -> None:
    op.drop_index("ix_missionapprentissage_derniere_session_tuteur_id", table_name="missionapprentissage")
    op.drop_index("ix_missionapprentissage_derniere_tentative_id", table_name="missionapprentissage")
    op.drop_index("ix_missionapprentissage_statut", table_name="missionapprentissage")
    op.drop_index("ix_missionapprentissage_etape", table_name="missionapprentissage")
    op.drop_index("ix_missionapprentissage_progression_id", table_name="missionapprentissage")
    op.drop_index("ix_missionapprentissage_utilisateur_id", table_name="missionapprentissage")
    op.drop_table("missionapprentissage")
