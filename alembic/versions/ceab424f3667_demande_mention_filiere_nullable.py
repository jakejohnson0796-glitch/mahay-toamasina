"""demandechangementfiliere : nouvelle_mention_id + nouvelle_filiere_id nullable

Revision ID: ceab424f3667
Revises: adb8b8883cd0
Create Date: 2026-09-11 09:00:00.000000

Complete le circuit d'approbation admin des changements de parcours
(voir admin_referentiel_router.py, actualiser_profil_academique() dans
auth_router.py) pour couvrir la mention en plus de la filiere, suite a
l'ajout de Utilisateur.mention_id (voir adb8b8883cd0) : une demande peut
desormais porter uniquement sur la mention (ex: retour ou passage au
tronc commun, ou changement de mention avant d'avoir choisi un parcours
precis), sans parcours cible -- d'ou nouvelle_filiere_id qui devient
nullable.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ceab424f3667'
down_revision: Union[str, None] = 'adb8b8883cd0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('demandechangementfiliere') as batch_op:
        batch_op.alter_column('nouvelle_filiere_id', existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column('nouvelle_mention_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_demande_nouvelle_mention', 'mention', ['nouvelle_mention_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('demandechangementfiliere') as batch_op:
        batch_op.drop_constraint('fk_demande_nouvelle_mention', type_='foreignkey')
        batch_op.drop_column('nouvelle_mention_id')
        batch_op.alter_column('nouvelle_filiere_id', existing_type=sa.Integer(), nullable=False)
