"""Tables persistantes pour les tournois Questions pour un champion."""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "bca6e2d8f143"
down_revision: Union[str, None] = "d5e9c7a1b3f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tournoichampion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("createur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("difficulte", sa.String(length=12), nullable=False, server_default="moyen"),
        sa.Column("statut", sa.String(length=16), nullable=False, server_default="attente"),
        sa.Column("questions_json", sa.Text(), nullable=False),
        sa.Column("index_question", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nb_questions", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("date_creation", sa.DateTime(), nullable=False),
        sa.Column("date_demarrage", sa.DateTime(), nullable=True),
        sa.Column("date_fin", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_tournoichampion_code", "tournoichampion", ["code"], unique=True)
    op.create_index("ix_tournoichampion_createur_id", "tournoichampion", ["createur_id"])
    op.create_index("ix_tournoichampion_statut", "tournoichampion", ["statut"])
    op.create_index("ix_tournoichampion_date_creation", "tournoichampion", ["date_creation"])
    op.create_index(
        "ix_tournoichampion_statut_date",
        "tournoichampion",
        ["statut", "date_creation"],
    )

    op.create_table(
        "participanttournoichampion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournoi_id", sa.Integer(), sa.ForeignKey("tournoichampion.id"), nullable=False),
        sa.Column("utilisateur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bonnes_reponses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("serie", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("date_adhesion", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "tournoi_id",
            "utilisateur_id",
            name="uq_participant_tournoi_utilisateur",
        ),
    )
    op.create_index(
        "ix_participanttournoichampion_tournoi_id",
        "participanttournoichampion",
        ["tournoi_id"],
    )
    op.create_index(
        "ix_participanttournoichampion_utilisateur_id",
        "participanttournoichampion",
        ["utilisateur_id"],
    )
    op.create_index(
        "ix_participant_tournoi_adhesion",
        "participanttournoichampion",
        ["tournoi_id", "date_adhesion"],
    )

    op.create_table(
        "reponsetournoichampion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournoi_id", sa.Integer(), sa.ForeignKey("tournoichampion.id"), nullable=False),
        sa.Column("utilisateur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("question_index", sa.Integer(), nullable=False),
        sa.Column("choix", sa.Integer(), nullable=False),
        sa.Column("correcte", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("date_reponse", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "tournoi_id",
            "utilisateur_id",
            "question_index",
            name="uq_reponse_tournoi_joueur_manche",
        ),
    )
    op.create_index(
        "ix_reponsetournoichampion_tournoi_id",
        "reponsetournoichampion",
        ["tournoi_id"],
    )
    op.create_index(
        "ix_reponsetournoichampion_utilisateur_id",
        "reponsetournoichampion",
        ["utilisateur_id"],
    )
    op.create_index(
        "ix_reponsetournoichampion_question_index",
        "reponsetournoichampion",
        ["question_index"],
    )
    op.create_index(
        "ix_reponse_tournoi_manche",
        "reponsetournoichampion",
        ["tournoi_id", "question_index"],
    )


def downgrade() -> None:
    op.drop_table("reponsetournoichampion")
    op.drop_table("participanttournoichampion")
    op.drop_table("tournoichampion")
