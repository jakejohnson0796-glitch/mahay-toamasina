"""systeme FAQ et feedback utilisateurs

Revision ID: 9f376861b81b
Revises: b3c7e5a1f9d4
Create Date: 2026-08-21 03:16:16.099744

Ajoute 3 tables pour la mission "FAQ + Feedback + Avis utilisateurs" :
- faq : questions/reponses publiques, categorisees, avec suppression
  logique (est_active) et ordre d'affichage manuel.
- feedback : avis d'un utilisateur (note 1-5 + commentaire), avec
  workflow de statut (nouveau -> en_cours -> repondu/resolu, ou masque
  par un admin) et un drapeau est_public que l'utilisateur controle
  lui-meme (defaut False, cf. Partie 14 du brief : confidentialite par
  defaut).
- reponsefeedback : reponse (unique, 1-1) d'un admin a un feedback,
  modifiable.

Note : l'autogenerate d'Alembic a aussi detecte plusieurs differences
sans rapport avec ce chantier (renommages d'index reflechis
differemment par SQLite, changement de type de colonne role) — elles
ne sont pas incluses ici pour rester strictement scope au systeme
FAQ/Feedback, conformement a la regle "ne pas modifier le code
existant sans rapport".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '9f376861b81b'
down_revision: Union[str, None] = 'b3c7e5a1f9d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'faq',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('question', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('reponse', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            'categorie',
            sa.Enum('GENERAL', 'COMPTE', 'COURS', 'QUIZ', 'CERCLES', 'IA', 'PROFIL',
                    'SECURITE', 'FEEDBACK', name='categoriefaq'),
            nullable=False,
        ),
        sa.Column('est_active', sa.Boolean(), nullable=False),
        sa.Column('ordre_affichage', sa.Integer(), nullable=False),
        sa.Column('cree_par_id', sa.Integer(), nullable=True),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.Column('date_modification', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['cree_par_id'], ['utilisateur.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_faq_categorie'), 'faq', ['categorie'], unique=False)
    op.create_index(op.f('ix_faq_est_active'), 'faq', ['est_active'], unique=False)

    op.create_table(
        'feedback',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('utilisateur_id', sa.Integer(), nullable=False),
        sa.Column('note', sa.Integer(), nullable=False),
        sa.Column('commentaire', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            'categorie',
            sa.Enum('GENERAL', 'COURS', 'QUIZ', 'CERCLES', 'IA', 'INTERFACE', 'BUG',
                    'SUGGESTION', 'AUTRE', name='categoriefeedback'),
            nullable=False,
        ),
        sa.Column(
            'statut',
            sa.Enum('NOUVEAU', 'EN_COURS', 'REPONDU', 'RESOLU', 'MASQUE', name='statutfeedback'),
            nullable=False,
        ),
        sa.Column('est_public', sa.Boolean(), nullable=False),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.Column('date_modification', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateur.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_feedback_date_creation'), 'feedback', ['date_creation'], unique=False)
    op.create_index('ix_feedback_note', 'feedback', ['note'], unique=False)
    op.create_index(op.f('ix_feedback_statut'), 'feedback', ['statut'], unique=False)
    op.create_index(op.f('ix_feedback_utilisateur_id'), 'feedback', ['utilisateur_id'], unique=False)

    op.create_table(
        'reponsefeedback',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('feedback_id', sa.Integer(), nullable=False),
        sa.Column('admin_id', sa.Integer(), nullable=False),
        sa.Column('reponse', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.Column('date_modification', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['admin_id'], ['utilisateur.id']),
        sa.ForeignKeyConstraint(['feedback_id'], ['feedback.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_reponsefeedback_feedback_id'), 'reponsefeedback', ['feedback_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_reponsefeedback_feedback_id'), table_name='reponsefeedback')
    op.drop_table('reponsefeedback')

    op.drop_index(op.f('ix_feedback_utilisateur_id'), table_name='feedback')
    op.drop_index(op.f('ix_feedback_statut'), table_name='feedback')
    op.drop_index('ix_feedback_note', table_name='feedback')
    op.drop_index(op.f('ix_feedback_date_creation'), table_name='feedback')
    op.drop_table('feedback')

    op.drop_index(op.f('ix_faq_est_active'), table_name='faq')
    op.drop_index(op.f('ix_faq_categorie'), table_name='faq')
    op.drop_table('faq')
