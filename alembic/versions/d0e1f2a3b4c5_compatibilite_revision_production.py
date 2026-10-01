"""Compatibilite Alembic pour une base de production ayant deja enregistre
la revision d0e1f2a3b4c5 lors d'un deploiement precedent.

La revision reste volontairement sans effet : le schema attendu par la version
courante est deja couvert par les migrations presentes dans le depot. Le but
est de conserver l'identifiant de revision connu par la base Supabase afin
qu'Alembic puisse reconstruire le graphe et poursuivre normalement le boot.
"""
from typing import Sequence, Union

from alembic import op  # noqa: F401


revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "7c4d9e2a1f60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No-op de compatibilite : la base de production a deja execute cette
    # revision lors d'un deploiement precedent.
    pass


def downgrade() -> None:
    pass
