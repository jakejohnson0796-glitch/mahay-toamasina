"""Lie chaque cours scolaire à son année académique de référence."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "x7e2a4c9b1d5"
down_revision: Union[str, Sequence[str], None] = "w6d9f3a1c2e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cours",
        sa.Column("annee_scolaire", sa.String(length=9), nullable=True),
    )
    op.create_index(
        "ix_cours_annee_scolaire",
        "cours",
        ["annee_scolaire"],
    )


def downgrade() -> None:
    op.drop_index("ix_cours_annee_scolaire", table_name="cours")
    op.drop_column("cours", "annee_scolaire")
