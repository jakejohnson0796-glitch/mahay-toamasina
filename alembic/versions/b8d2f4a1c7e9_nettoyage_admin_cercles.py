"""nettoyage des appartenances administrateurs redondantes

Revision ID: b8d2f4a1c7e9
Revises: a6c9e2f4b7d1

Les administrateurs globaux sont autorises a acceder a tous les cercles par
la logique de permission applicative. Ils ne doivent donc plus etre
materialises comme membres de chaque cercle. Cette migration supprime les
anciennes lignes MembreCercle appartenant a un admin global, sauf si cet
admin est le createur reel du cercle (son role CREATEUR reste necessaire
pour conserver l'invariant createur -> membre).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b8d2f4a1c7e9"
down_revision: Union[str, None] = "a6c9e2f4b7d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        """
        DELETE FROM membrecercle
        WHERE utilisateur_id IN (
            SELECT id FROM utilisateur WHERE CAST(role AS TEXT) = 'ADMIN'
        )
        AND NOT EXISTS (
            SELECT 1
            FROM cercleetude
            WHERE cercleetude.id = membrecercle.cercle_id
              AND cercleetude.createur_id = membrecercle.utilisateur_id
        )
        """
    ))


def downgrade() -> None:
    # Impossible de reconstruire de facon fiable les anciennes appartenances
    # globales sans historique : l'acces admin est maintenant gere par role.
    pass
