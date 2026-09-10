"""mot de passe oublie : email, doit_changer_mot_de_passe, table des codes

Revision ID: 526f828e83d2
Revises: 2011de266286
Create Date: 2026-09-09 14:00:00.000000

Trois ajouts lies a la fonctionnalite "mot de passe oublie" (envoi par
EMAIL, gratuit -- voir app/email_utils.py -- contrairement a un envoi de
SMS) :
- Utilisateur.email (nullable) : canal de secours facultatif, renseigne
  par l'utilisateur sur /securite. L'identifiant de connexion reste le
  telephone, cet email ne sert qu'a recevoir le code de reinitialisation.
- Utilisateur.doit_changer_mot_de_passe (nullable=False, defaut False) :
  drapeau pose apres une reinitialisation admin ou par email, efface
  quand l'utilisateur definit lui-meme un nouveau mot de passe.
- CodeReinitialisationMotDePasse : table des codes a 6 chiffres envoyes
  par email (voir /mot-de-passe-oublie dans auth_router.py), sur le
  meme modele que CodeSecours2FA mais avec une expiration courte.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '526f828e83d2'
down_revision: Union[str, None] = '2011de266286'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('utilisateur', sa.Column('email', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column(
        'utilisateur',
        sa.Column('doit_changer_mot_de_passe', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        'codereinitialisationmotdepasse',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('utilisateur_id', sa.Integer(), nullable=False),
        sa.Column('code_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('expire_le', sa.DateTime(), nullable=False),
        sa.Column('utilise', sa.Boolean(), nullable=False),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateur.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('codereinitialisationmotdepasse')
    op.drop_column('utilisateur', 'doit_changer_mot_de_passe')
    op.drop_column('utilisateur', 'email')
