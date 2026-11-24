"""Persist the selected locale for generated quizzes and AI tutor sessions."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b7c3e9a1d5f2"
down_revision: Union[str, Sequence[str], None] = "z3a9c7d1e5f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tentativequiz",
        sa.Column("langue", sa.String(length=5), nullable=False, server_default="fr"),
    )
    op.create_index("ix_tentativequiz_langue", "tentativequiz", ["langue"])
    op.add_column(
        "sessiontuteur",
        sa.Column("langue", sa.String(length=5), nullable=False, server_default="fr"),
    )
    op.create_index("ix_sessiontuteur_langue", "sessiontuteur", ["langue"])
    op.add_column(
        "analysecomparativelecon",
        sa.Column("langue", sa.String(length=5), nullable=False, server_default="fr"),
    )
    op.create_index(
        "ix_analysecomparativelecon_langue",
        "analysecomparativelecon",
        ["langue"],
    )


def downgrade() -> None:
    op.drop_index("ix_analysecomparativelecon_langue", table_name="analysecomparativelecon")
    op.drop_column("analysecomparativelecon", "langue")
    op.drop_index("ix_sessiontuteur_langue", table_name="sessiontuteur")
    op.drop_column("sessiontuteur", "langue")
    op.drop_index("ix_tentativequiz_langue", table_name="tentativequiz")
    op.drop_column("tentativequiz", "langue")
