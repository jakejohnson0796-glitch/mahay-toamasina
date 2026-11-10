"""Classe les annales BEPC 2027 selon le programme réellement suivi."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l6d8b2f1a4c9"
down_revision: Union[str, Sequence[str], None] = "k3f8a1d6c9b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document",
        sa.Column("bepc_session_2027_parcours", sa.String(length=8), nullable=True),
    )
    op.create_index(
        "ix_document_bepc_session_2027_parcours",
        "document",
        ["bepc_session_2027_parcours"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_bepc_session_2027_parcours",
        table_name="document",
    )
    op.drop_column("document", "bepc_session_2027_parcours")
