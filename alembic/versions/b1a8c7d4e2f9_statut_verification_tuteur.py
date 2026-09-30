"""Suivi asynchrone de la verification multi-modeles du Tuteur IA."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1a8c7d4e2f9"
down_revision: Union[str, None] = "9e5b7c1a2d40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessiontuteur",
        sa.Column(
            "statut_verification_ia",
            sa.String(),
            nullable=False,
            server_default="en_attente",
        ),
    )
    op.add_column(
        "sessiontuteur",
        sa.Column("date_verification_ia", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "sessiontuteur",
        sa.Column("erreur_verification_ia", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_sessiontuteur_statut_verification_ia",
        "sessiontuteur",
        ["statut_verification_ia"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sessiontuteur_statut_verification_ia",
        table_name="sessiontuteur",
    )
    op.drop_column("sessiontuteur", "erreur_verification_ia")
    op.drop_column("sessiontuteur", "date_verification_ia")
    op.drop_column("sessiontuteur", "statut_verification_ia")
