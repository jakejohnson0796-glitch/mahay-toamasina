"""Backfill de CercleEtude.mention_id depuis Filiere.mention_id.

Revision ID: f4b7c9d1e2a6
Revises: c1e7f4a2b9d6

Les cercles crees avant l'introduction de mention_id possedent parfois
filiere_id mais mention_id=NULL. Le referentiel academique national
definit la mention d'une telle filiere ; recopier cette FK permet a la
recherche et a l'affichage des cercles d'utiliser la meme hierarchie
Domaine -> Mention -> Niveau -> Parcours sans casser les cercles libres.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f4b7c9d1e2a6"
down_revision: Union[str, None] = "c1e7f4a2b9d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # Requete volontairement portable SQLite + PostgreSQL :
    # une sous-requete correlee remplace UPDATE ... FROM, car cette migration
    # s'execute aussi dans la CI SQLite.
    conn.execute(sa.text(
        """
        UPDATE cercleetude
        SET mention_id = (
            SELECT f.mention_id
            FROM filiere f
            WHERE f.id = cercleetude.filiere_id
        )
        WHERE cercleetude.mention_id IS NULL
          AND cercleetude.filiere_id IS NOT NULL
          AND EXISTS (
              SELECT 1
              FROM filiere f2
              WHERE f2.id = cercleetude.filiere_id
                AND f2.mention_id IS NOT NULL
          )
        """
    ))


def downgrade() -> None:
    # Le backfill ne doit pas effacer les mentions ajoutees ou corrigees
    # apres le deploiement. Aucun rollback destructif.
    pass
