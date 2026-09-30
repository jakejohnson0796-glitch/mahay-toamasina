"""Suivi du parcours de demarrage et des 7 premiers jours."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e4f9a1b2c3"
down_revision: Union[str, None] = "c4d9e8f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("utilisateur", sa.Column("onboarding_commence_le", sa.DateTime(), nullable=True))
    op.add_column("utilisateur", sa.Column("onboarding_termine_le", sa.DateTime(), nullable=True))
    op.create_index("ix_utilisateur_onboarding_commence_le", "utilisateur", ["onboarding_commence_le"])
    op.create_index("ix_utilisateur_onboarding_termine_le", "utilisateur", ["onboarding_termine_le"])


def downgrade() -> None:
    op.drop_index("ix_utilisateur_onboarding_termine_le", table_name="utilisateur")
    op.drop_index("ix_utilisateur_onboarding_commence_le", table_name="utilisateur")
    op.drop_column("utilisateur", "onboarding_termine_le")
    op.drop_column("utilisateur", "onboarding_commence_le")
