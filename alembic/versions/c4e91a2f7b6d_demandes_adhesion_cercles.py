"""demandes d'adhesion aux cercles d'etude

Revision ID: c4e91a2f7b6d
Revises: 6ce046f6408e
Create Date: 2026-08-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'c4e91a2f7b6d'
down_revision: Union[str, None] = '6ce046f6408e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'demandeadhesioncercle',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cercle_id', sa.Integer(), nullable=False),
        sa.Column('utilisateur_id', sa.Integer(), nullable=False),
        sa.Column('statut', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.Column('date_traitement', sa.DateTime(), nullable=True),
        sa.Column('traite_par_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['cercle_id'], ['cercleetude.id'], ),
        sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateur.id'], ),
        sa.ForeignKeyConstraint(['traite_par_id'], ['utilisateur.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    # Index unique PARTIEL : une seule demande "en_attente" a la fois par
    # (cercle, utilisateur) — empeche le doublon au niveau base, en plus
    # de la verification applicative dans cercles_router.py (defense en
    # profondeur : protege meme en cas de requetes concurrentes).
    #
    # IMPORTANT : SQLModel/SQLAlchemy stocke les colonnes Enum(str, Enum)
    # via le NOM du membre Python (ex: "EN_ATTENTE"), pas sa valeur (ex:
    # "en_attente") — comportement deja en place pour tous les autres
    # champs enum du projet (RoleUtilisateur, StatutDocument...). La
    # clause WHERE ci-dessous doit donc comparer a la chaine en
    # MAJUSCULES pour matcher ce qui est reellement ecrit en base ;
    # utiliser la valeur minuscule ferait que l'index ne matcherait
    # jamais aucune ligne et la contrainte serait silencieusement
    # inoperante (verifie manuellement avant d'ecrire cette migration).
    #
    # Ecrit avec les deux variantes de clause WHERE pour fonctionner a
    # l'identique sur SQLite (dev local) et PostgreSQL (Supabase/Render).
    op.create_index(
        'ix_demande_unique_en_attente',
        'demandeadhesioncercle',
        ['cercle_id', 'utilisateur_id'],
        unique=True,
        postgresql_where=sa.text("statut = 'EN_ATTENTE'"),
        sqlite_where=sa.text("statut = 'EN_ATTENTE'"),
    )


def downgrade() -> None:
    op.drop_index('ix_demande_unique_en_attente', table_name='demandeadhesioncercle')
    op.drop_table('demandeadhesioncercle')
