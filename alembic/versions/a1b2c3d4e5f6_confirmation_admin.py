"""Ajoute un mot de passe distinct pour confirmer les actions admin."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f8a2c6e4b1d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(inspector, table: str) -> set[str]:
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("utilisateur"):
        raise RuntimeError("La table 'utilisateur' est absente avant la migration admin.")

    cols = _cols(inspector, "utilisateur")
    if "mot_de_passe_confirmation_admin_hash" not in cols:
        op.add_column(
            "utilisateur",
            sa.Column("mot_de_passe_confirmation_admin_hash", sa.String(), nullable=True),
        )
    if "confirmation_admin_configuree_le" not in cols:
        op.add_column(
            "utilisateur",
            sa.Column("confirmation_admin_configuree_le", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("utilisateur"):
        return
    cols = _cols(inspector, "utilisateur")
    if "confirmation_admin_configuree_le" in cols:
        op.drop_column("utilisateur", "confirmation_admin_configuree_le")
    if "mot_de_passe_confirmation_admin_hash" in cols:
        op.drop_column("utilisateur", "mot_de_passe_confirmation_admin_hash")
