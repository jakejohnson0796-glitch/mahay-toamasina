"""Evenements XP et gamification quotidienne."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d9e8f1a2b3"
down_revision: Union[str, None] = "b1a8c7d4e2f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _indexes(inspector, table: str) -> set[str]:
    return {i["name"] for i in inspector.get_indexes(table) if i.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("actiongamification"):
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
    else:
        cols = {c["name"] for c in inspector.get_columns("actiongamification")}
        for name, column in {
            "id": sa.Column("id", sa.Integer(), nullable=True),
            "utilisateur_id": sa.Column("utilisateur_id", sa.Integer(), nullable=True),
            "action": sa.Column("action", sa.String(), nullable=True),
            "source_type": sa.Column("source_type", sa.String(), nullable=True, server_default=""),
            "source_key": sa.Column("source_key", sa.String(), nullable=True, server_default=""),
            "points": sa.Column("points", sa.Integer(), nullable=True),
            "date_creation": sa.Column("date_creation", sa.DateTime(), nullable=True),
        }.items():
            if name not in cols:
                op.add_column("actiongamification", column)

        inspector = sa.inspect(bind)
        unique_cols = ("utilisateur_id", "action", "source_type", "source_key")
        uniques = inspector.get_unique_constraints("actiongamification")
        if not any(tuple(u.get("column_names") or ()) == unique_cols for u in uniques):
            op.create_unique_constraint(
                "uq_action_gamification_source",
                "actiongamification",
                list(unique_cols),
            )

    inspector = sa.inspect(bind)
    indexes = _indexes(inspector, "actiongamification")
    targets = {
        "ix_actiongamification_utilisateur_id": ["utilisateur_id"],
        "ix_actiongamification_action": ["action"],
        "ix_actiongamification_source_type": ["source_type"],
        "ix_actiongamification_date_creation": ["date_creation"],
    }
    for name, cols in targets.items():
        if name not in indexes:
            op.create_index(name, "actiongamification", cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("actiongamification"):
        return
    indexes = _indexes(inspector, "actiongamification")
    for name in (
        "ix_actiongamification_date_creation",
        "ix_actiongamification_source_type",
        "ix_actiongamification_action",
        "ix_actiongamification_utilisateur_id",
    ):
        if name in indexes:
            op.drop_index(name, table_name="actiongamification")
    op.drop_table("actiongamification")
