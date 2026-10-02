"""Suivi du parcours de demarrage et des 7 premiers jours."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e4f9a1b2c3"
down_revision: Union[str, None] = "c4d9e8f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(inspector, table: str) -> set[str]:
    return {c["name"] for c in inspector.get_columns(table)}


def _indexes(inspector, table: str) -> set[str]:
    return {i["name"] for i in inspector.get_indexes(table) if i.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("utilisateur"):
        raise RuntimeError("La table 'utilisateur' est absente avant la migration onboarding.")

    cols = _cols(inspector, "utilisateur")
    additions = {
        "onboarding_commence_le": sa.Column("onboarding_commence_le", sa.DateTime(), nullable=True),
        "onboarding_termine_le": sa.Column("onboarding_termine_le", sa.DateTime(), nullable=True),
    }
    for name, column in additions.items():
        if name not in cols:
            op.add_column("utilisateur", column)

    inspector = sa.inspect(bind)
    indexes = _indexes(inspector, "utilisateur")
    if "ix_utilisateur_onboarding_commence_le" not in indexes:
        op.create_index(
            "ix_utilisateur_onboarding_commence_le",
            "utilisateur",
            ["onboarding_commence_le"],
        )
    if "ix_utilisateur_onboarding_termine_le" not in indexes:
        op.create_index(
            "ix_utilisateur_onboarding_termine_le",
            "utilisateur",
            ["onboarding_termine_le"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("utilisateur"):
        return
    indexes = _indexes(inspector, "utilisateur")
    if "ix_utilisateur_onboarding_termine_le" in indexes:
        op.drop_index("ix_utilisateur_onboarding_termine_le", table_name="utilisateur")
    if "ix_utilisateur_onboarding_commence_le" in indexes:
        op.drop_index("ix_utilisateur_onboarding_commence_le", table_name="utilisateur")
    cols = _cols(inspector, "utilisateur")
    if "onboarding_termine_le" in cols:
        op.drop_column("utilisateur", "onboarding_termine_le")
    if "onboarding_commence_le" in cols:
        op.drop_column("utilisateur", "onboarding_commence_le")
