"""photo de profil utilisateur (upload reel ou avatar auto-genere)

Revision ID: b35199e31b78
Revises: c4a9e7f1b3d6
Create Date: 2026-09-07 10:00:00.000000

Ajoute la possibilite pour un compte (etudiant, sponsor, professeur ou
admin) d'uploader une vraie photo de profil (voir app/storage.py,
sauvegarder_avatar()). Nullable et purement additif : un compte sans
photo (le cas de tous les comptes existants juste apres cette
migration) affiche a la place un avatar genere automatiquement
(initiale + couleur deterministe, voir couleur_avatar() dans
app/templating.py) -- deja utilise ailleurs sur le site (chat des
cercles d'etude), desormais generalise via components/avatar.html a
tout endroit ou un utilisateur est affiche (sidebar, liste des
membres, administration).

Meme convention que Document.chemin_fichier (voir app/storage.py) :
photo_chemin est une reference OPAQUE (chemin local relatif, ou cle
d'objet dans le bucket Supabase) qui ne doit jamais etre construite ou
interpretee ailleurs que dans app/storage.py -- l'affichage passe
toujours par la route /profil/photo/{utilisateur_id} (voir
auth_router.py), jamais par ce champ directement dans un template.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'b35199e31b78'
down_revision: Union[str, None] = 'c4a9e7f1b3d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('utilisateur', sa.Column('photo_chemin', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    op.drop_column('utilisateur', 'photo_chemin')
