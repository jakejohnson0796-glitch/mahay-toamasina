"""Ajoute un mot de passe distinct pour confirmer les actions admin."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f8a2c6e4b1d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "utilisateur",
        sa.Column("mot_de_passe_confirmation_admin_hash", sa.String(), nullable=True),
    )
    op.add_column(
        "utilisateur",
        sa.Column("confirmation_admin_configuree_le", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("utilisateur", "confirmation_admin_configuree_le")
    op.drop_column("utilisateur", "mot_de_passe_confirmation_admin_hash")
