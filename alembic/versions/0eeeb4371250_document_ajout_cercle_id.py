"""document : ajout de cercle_id (portee cercle optionnelle)

Revision ID: 0eeeb4371250
Revises: ceab424f3667
Create Date: 2026-09-19 00:00:00.000000

Ajoute Document.cercle_id (nullable, FK vers cercleetude.id) : un document
peut desormais etre rattache a un cercle d'etude precis en plus d'etre
visible dans la bibliotheque generale (/documents), qui reste filtree par
filiere/matiere/type comme avant. None pour toutes les lignes existantes
et pour tout document uploade directement depuis la bibliotheque (sans
passer par un cercle) -- comportement inchange.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0eeeb4371250'
down_revision: Union[str, None] = 'ceab424f3667'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('document') as batch_op:
        batch_op.add_column(sa.Column('cercle_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_document_cercle', 'cercleetude', ['cercle_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('document') as batch_op:
        batch_op.drop_constraint('fk_document_cercle', type_='foreignkey')
        batch_op.drop_column('cercle_id')
