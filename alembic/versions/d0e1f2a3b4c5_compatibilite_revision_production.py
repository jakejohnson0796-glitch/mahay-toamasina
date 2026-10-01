"""Compatibilite Alembic pour la base de production.

La base de production a deja rencontre la revision d0e1f2a3b4c5.
Cette revision sans effet permet a Alembic de reconstruire le graphe sur une
installation neuve comme sur la base existante.
"""
from typing import Sequence, Union
from alembic import op  # noqa: F401

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9f1a7e4b3d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
