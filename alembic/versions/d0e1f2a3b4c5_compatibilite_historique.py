"""Migration-pont pour une revision historique presente en production.

Cette revision existait dans certaines bases deployees sous l'identifiant
"d0e1f2a3b4c5" mais son fichier a disparu du depot. Elle est volontairement
sans effet : elle permet a Alembic de reconnaitre la version stockee en base
et de reprendre la chaine normale a partir de e7f1a9c3d5b7.

Revision ID: d0e1f2a3b4c5
Revises: e7f1a9c3d5b7
"""

from typing import Sequence, Union

from alembic import op  # noqa: F401


revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "e7f1a9c3d5b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Pont de compatibilite uniquement : aucune modification de schema.
    pass


def downgrade() -> None:
    pass
