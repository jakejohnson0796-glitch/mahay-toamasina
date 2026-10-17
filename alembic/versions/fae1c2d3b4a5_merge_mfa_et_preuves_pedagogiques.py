"""Reunit les branches Alembic indépendantes MFA et preuves pédagogiques."""
from typing import Sequence, Union


revision: str = "fae1c2d3b4a5"
down_revision: Union[str, Sequence[str], None] = ("d3f6a9c1e2b4", "f9b8d3a6c2e1")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Migration de fusion uniquement : chaque parent applique déjà ses changements.
    pass


def downgrade() -> None:
    # Aucun changement de schéma propre à cette révision.
    pass
