"""prix sponsor negocie apres contact (plus de prix fixe affiche)

Revision ID: 30de0154f0ca
Revises: f2b8e6a1c9d3
Create Date: 2026-08-19 00:00:00.000000

Le prix sponsor n'est plus fixe a l'avance sur le site : chaque sponsor
est different (repetiteur individuel, petit commerce, service...), donc
le prix est desormais negocie directement avec lui apres un premier
contact, pas impose publiquement. Deux changements sur la table
`abonnement` :
- `prix_ariary` devient nullable : vide tant que le prix n'a pas ete
  negocie, rempli par un admin une fois l'accord trouve hors-ligne.
  Les lignes existantes (creees sous l'ancien prix fixe) gardent leur
  valeur telle quelle, rien n'est efface.
- ajout de `message` (texte libre, nullable) : contexte que le sponsor
  donne en envoyant sa demande de contact (activite, besoin...).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "30de0154f0ca"
down_revision: Union[str, None] = "f2b8e6a1c9d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table : SQLite ne supporte pas ALTER COLUMN directement,
    # Alembic recree la table en coulisses dans ce mode. Fonctionne aussi
    # tel quel sur Postgres (Supabase), ou ça reste un simple ALTER COLUMN.
    with op.batch_alter_table("abonnement") as batch_op:
        batch_op.add_column(sa.Column("message", sa.String(), nullable=True))
        batch_op.alter_column("prix_ariary", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # Les demandes envoyees sans prix (nouveau flux) n'ont pas de valeur a
    # remettre : on force 0 par defaut pour pouvoir repasser la colonne en
    # NOT NULL sans erreur, plutot que de perdre ces lignes.
    op.execute("UPDATE abonnement SET prix_ariary = 0 WHERE prix_ariary IS NULL")
    with op.batch_alter_table("abonnement") as batch_op:
        batch_op.alter_column("prix_ariary", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("message")
