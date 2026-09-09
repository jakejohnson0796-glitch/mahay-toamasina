"""bio ("a propos") utilisateur pour le panneau profil du chat de cercle

Revision ID: 2011de266286
Revises: b35199e31b78
Create Date: 2026-09-09 09:00:00.000000

Ajoute un champ texte court, facultatif, affiche dans le panneau "Profil
de l'utilisateur" ouvert en cliquant sur un avatar/nom dans le chat d'un
cercle d'etude (voir GET /cercles/{cercle_id}/membres/{utilisateur_id}/profil
dans cercles_router.py). Nullable et purement additif : un compte sans
bio (tous les comptes existants juste apres cette migration) n'affiche
simplement pas de section "A propos" dans ce panneau.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '2011de266286'
down_revision: Union[str, None] = 'b35199e31b78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('utilisateur', sa.Column('bio', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    op.drop_column('utilisateur', 'bio')
