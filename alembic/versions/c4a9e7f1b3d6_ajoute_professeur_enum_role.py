"""ajoute PROFESSEUR au type enum roleutilisateur (bug pre-existant)

Revision ID: c4a9e7f1b3d6
Revises: b8f4d1c6a2e7
Create Date: 2026-08-23 18:00:00.000000

Bug decouvert en testant le rattachement de la banniere
PROFILE_ACADEMIC_UPDATE_REQUIRED aux comptes professeur (§21-22) :
le role PROFESSEUR existe dans le modele Python (app/models.py,
RoleUtilisateur) depuis un moment et est deja utilise par
admin_router.py (promotion d'un utilisateur) et classe_router.py
(Classe virtuelle), mais AUCUNE migration n'a jamais ajoute
'PROFESSEUR' au type enum natif Postgres 'roleutilisateur' — cree par
la migration de baseline avec seulement ('ETUDIANT', 'SPONSOR',
'ADMIN'). Consequence : toute tentative de creer ou promouvoir un
compte en professeur echoue en production avec une erreur Postgres
(invalid input value for enum roleutilisateur), meme si SQLite (utilise
en dev local) ne l'aurait jamais revele — SQLite n'a pas de type enum
natif, juste du texte libre, donc aucune contrainte ne s'y applique.

ALTER TYPE ... ADD VALUE est sans danger sur les lignes existantes
(purement additif, aucune ligne 'PROFESSEUR' ne pouvait de toute facon
exister avant cette migration) et compatible avec le mode transactionnel
d'Alembic sur Postgres 12+, tant que la nouvelle valeur n'est pas
utilisee dans la MEME transaction (ce que cette migration ne fait pas).
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c4a9e7f1b3d6'
down_revision: Union[str, None] = 'b8f4d1c6a2e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sur SQLite (dev local), le type 'roleutilisateur' n'existe pas en
    # tant que tel (colonne texte libre) : rien a faire, cette migration
    # est un no-op silencieux dans ce cas plutot qu'une erreur.
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # Executee hors du bloc transactionnel implicite d'Alembic : plus
    # sur que de compter sur le support transactionnel d'ALTER TYPE
    # ADD VALUE, qui varie encore selon la version exacte de Postgres.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE roleutilisateur ADD VALUE IF NOT EXISTS 'PROFESSEUR'")


def downgrade() -> None:
    # Postgres ne permet pas de retirer une valeur d'un type enum
    # existant (il faudrait recreer le type entierement et migrer
    # toutes les colonnes qui l'utilisent). Si une vraie annulation est
    # necessaire un jour, elle devra etre ecrite a la main avec le
    # contexte precis du moment (colonnes affectees, lignes existantes
    # avec role='professeur' a reassigner d'abord).
    raise NotImplementedError(
        "Postgres ne supporte pas de retirer une valeur d'un type enum. "
        "Voir le commentaire de cette fonction pour la marche a suivre manuelle."
    )
