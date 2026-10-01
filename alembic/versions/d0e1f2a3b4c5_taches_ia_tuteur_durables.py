"""Rend la file IA generique pour le Tuteur."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9f1a7e4b3d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tacheia", recreate="always") as batch_op:
        batch_op.alter_column(
            "tentative_quiz_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.add_column(
            sa.Column("session_tuteur_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_tacheia_session_tuteur_id",
            "sessiontuteur",
            ["session_tuteur_id"],
            ["id"],
        )
        batch_op.create_unique_constraint(
            "uq_tache_ia_type_tuteur",
            ["type_tache", "session_tuteur_id"],
        )
        batch_op.create_index(
            "ix_tacheia_session_tuteur_id",
            ["session_tuteur_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("tacheia", recreate="always") as batch_op:
        batch_op.drop_index("ix_tacheia_session_tuteur_id")
        batch_op.drop_constraint("uq_tache_ia_type_tuteur", type_="unique")
        batch_op.drop_constraint("fk_tacheia_session_tuteur_id", type_="foreignkey")
        batch_op.drop_column("session_tuteur_id")
        batch_op.alter_column(
            "tentative_quiz_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
