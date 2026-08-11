"""devoirs et rendus (classe virtuelle)

Revision ID: 4f7a1d6e9c02
Revises: 9b2e5f8c3a41
Create Date: 2026-08-10 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '4f7a1d6e9c02'
down_revision: Union[str, None] = '9b2e5f8c3a41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'devoir',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cours_id', sa.Integer(), nullable=False),
        sa.Column('titre', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('date_limite', sa.DateTime(), nullable=True),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['cours_id'], ['cours.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'rendudevoir',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('devoir_id', sa.Integer(), nullable=False),
        sa.Column('utilisateur_id', sa.Integer(), nullable=False),
        sa.Column('chemin_fichier', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('nom_fichier_original', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('commentaire', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('date_rendu', sa.DateTime(), nullable=False),
        sa.Column('note', sa.Float(), nullable=True),
        sa.Column('appreciation_prof', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('date_correction', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['devoir_id'], ['devoir.id'], ),
        sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateur.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    # Un seul rendu "vivant" par (devoir, etudiant) — un nouveau depot
    # remplace l'ancien plutot que d'empiler des doublons (voir
    # rendre_devoir() dans classe_router.py, qui fait un update-or-insert).
    op.create_index('ix_rendu_unique', 'rendudevoir', ['devoir_id', 'utilisateur_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_rendu_unique', table_name='rendudevoir')
    op.drop_table('rendudevoir')
    op.drop_table('devoir')
