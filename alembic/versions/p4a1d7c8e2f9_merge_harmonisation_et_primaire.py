"""Fusionne les branches primaire/CEPE et harmonisation des cours."""

from typing import Sequence, Union

from alembic import op


revision: str = "p4a1d7c8e2f9"
down_revision: Union[str, Sequence[str], None] = (
    "c3e8f1a6b9d2",
    "n2b3c4d5e6f7",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Les deux branches ont déjà appliqué leurs propres changements.
    # Cette révision ne fait que réunifier le graphe Alembic.
    pass


def downgrade() -> None:
    # Un downgrade de cette révision ne doit pas annuler les deux branches.
    pass
