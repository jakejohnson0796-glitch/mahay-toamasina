"""classe virtuelle : cours, seances, inscriptions, presences

Revision ID: 7d3f4c9a1e28
Revises: c4e91a2f7b6d
Create Date: 2026-08-08 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '7d3f4c9a1e28'
down_revision: Union[str, None] = 'c4e91a2f7b6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cours',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nom', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('matiere', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('niveau', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('professeur_id', sa.Integer(), nullable=False),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['professeur_id'], ['utilisateur.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'inscriptioncours',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cours_id', sa.Integer(), nullable=False),
        sa.Column('utilisateur_id', sa.Integer(), nullable=False),
        sa.Column('date_inscription', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['cours_id'], ['cours.id'], ),
        sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateur.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    # Un etudiant ne peut etre inscrit qu'une seule fois au meme cours.
    op.create_index('ix_inscription_unique', 'inscriptioncours', ['cours_id', 'utilisateur_id'], unique=True)

    op.create_table(
        'seance',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cours_id', sa.Integer(), nullable=False),
        sa.Column('titre', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('statut', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('nom_salle_livekit', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('date_debut_reelle', sa.DateTime(), nullable=True),
        sa.Column('date_fin_reelle', sa.DateTime(), nullable=True),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['cours_id'], ['cours.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nom_salle_livekit'),
    )

    op.create_table(
        'presenceseance',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('seance_id', sa.Integer(), nullable=False),
        sa.Column('utilisateur_id', sa.Integer(), nullable=False),
        sa.Column('heure_entree', sa.DateTime(), nullable=False),
        sa.Column('heure_sortie', sa.DateTime(), nullable=True),
        sa.Column('duree_estimee_secondes', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['seance_id'], ['seance.id'], ),
        sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateur.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('presenceseance')
    op.drop_table('seance')
    op.drop_index('ix_inscription_unique', table_name='inscriptioncours')
    op.drop_table('inscriptioncours')
    op.drop_table('cours')
