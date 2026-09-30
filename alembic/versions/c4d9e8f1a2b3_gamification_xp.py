"""Evenements XP et gamification quotidienne."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d9e8f1a2b3"
down_revision: Union[str, None] = "b1a8c7d4e2f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "actiongamification",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("utilisateur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False, server_default=""),
        sa.Column("source_key", sa.String(), nullable=False, server_default=""),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("date_creation", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "utilisateur_id",
            "action",
            "source_type",
            "source_key",
            name="uq_action_gamification_source",
        ),
    )
    op.create_index("ix_actiongamification_utilisateur_id", "actiongamification", ["utilisateur_id"])
    op.create_index("ix_actiongamification_action", "actiongamification", ["action"])
    op.create_index("ix_actiongamification_source_type", "actiongamification", ["source_type"])
    op.create_index("ix_actiongamification_date_creation", "actiongamification", ["date_creation"])


def downgrade() -> None:
    op.drop_index("ix_actiongamification_date_creation", table_name="actiongamification")
    op.drop_index("ix_actiongamification_source_type", table_name="actiongamification")
    op.drop_index("ix_actiongamification_action", table_name="actiongamification")
    op.drop_index("ix_actiongamification_utilisateur_id", table_name="actiongamification")
    op.drop_table("actiongamification")
