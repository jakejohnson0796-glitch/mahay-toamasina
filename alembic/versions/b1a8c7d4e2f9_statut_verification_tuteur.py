"""Suivi asynchrone de la verification multi-modeles du Tuteur IA."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1a8c7d4e2f9"
down_revision: Union[str, None] = "9e5b7c1a2d40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(inspector, table: str) -> set[str]:
    return {c["name"] for c in inspector.get_columns(table)}


def _indexes(inspector, table: str) -> set[str]:
    return {i["name"] for i in inspector.get_indexes(table) if i.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("sessiontuteur"):
        raise RuntimeError("La table 'sessiontuteur' est absente avant la migration Tuteur.")

    cols = _cols(inspector, "sessiontuteur")
    additions = {
        "statut_verification_ia": sa.Column(
            "statut_verification_ia", sa.String(), nullable=False, server_default="en_attente"
        ),
        "date_verification_ia": sa.Column(
            "date_verification_ia", sa.DateTime(), nullable=True
        ),
        "erreur_verification_ia": sa.Column(
            "erreur_verification_ia", sa.String(), nullable=True
        ),
    }
    for name, column in additions.items():
        if name not in cols:
            op.add_column("sessiontuteur", column)

    inspector = sa.inspect(bind)
    if "ix_sessiontuteur_statut_verification_ia" not in _indexes(inspector, "sessiontuteur"):
        op.create_index(
            "ix_sessiontuteur_statut_verification_ia",
            "sessiontuteur",
            ["statut_verification_ia"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("sessiontuteur"):
        return
    indexes = _indexes(inspector, "sessiontuteur")
    if "ix_sessiontuteur_statut_verification_ia" in indexes:
        op.drop_index("ix_sessiontuteur_statut_verification_ia", table_name="sessiontuteur")
    cols = _cols(inspector, "sessiontuteur")
    for name in (
        "erreur_verification_ia",
        "date_verification_ia",
        "statut_verification_ia",
    ):
        if name in cols:
            op.drop_column("sessiontuteur", name)
