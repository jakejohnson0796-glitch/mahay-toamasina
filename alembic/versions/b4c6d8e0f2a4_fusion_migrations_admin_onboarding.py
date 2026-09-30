"""Fusionne les deux branches de migrations Alembic actives.

Les migrations d'onboarding et de confirmation admin ont été créées sur
des branches différentes de la chaîne principale. Cette migration de fusion
permet à Alembic de disposer d'une seule tête avant le prochain démarrage.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b4c6d8e0f2a4"
down_revision: Union[str, Sequence[str], None] = (
    "a1b2c3d4e5f6",
    "d7e4f9a1b2c3",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Migration de fusion uniquement : les deux branches ont déjà appliqué
    # leurs changements de schéma respectifs.
    pass


def downgrade() -> None:
    # Aucun changement de schéma propre à cette migration.
    pass
