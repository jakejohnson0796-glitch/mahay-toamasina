"""tableau blanc collaboratif (classe virtuelle)

Revision ID: 9b2e5f8c3a41
Revises: 7d3f4c9a1e28
Create Date: 2026-08-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '9b2e5f8c3a41'
down_revision: Union[str, None] = '7d3f4c9a1e28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'evenementtableaublanc',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('seance_id', sa.Integer(), nullable=False),
        sa.Column('utilisateur_id', sa.Integer(), nullable=False),
        sa.Column('type_evenement', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('element_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('donnees', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['seance_id'], ['seance.id'], ),
        sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateur.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    # Accelere la reconstitution de l'etat (SELECT ... WHERE seance_id=...
    # ORDER BY date_creation) et la lecture rapide de l'historique complet
    # d'une seance a l'ouverture du tableau.
    op.create_index('ix_evenement_tableau_seance', 'evenementtableaublanc', ['seance_id', 'date_creation'])

    op.create_table(
        'autorisationecrituretableau',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('seance_id', sa.Integer(), nullable=False),
        sa.Column('utilisateur_id', sa.Integer(), nullable=False),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['seance_id'], ['seance.id'], ),
        sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateur.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_autorisation_unique', 'autorisationecrituretableau', ['seance_id', 'utilisateur_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_autorisation_unique', table_name='autorisationecrituretableau')
    op.drop_table('autorisationecrituretableau')
    op.drop_index('ix_evenement_tableau_seance', table_name='evenementtableaublanc')
    op.drop_table('evenementtableaublanc')
