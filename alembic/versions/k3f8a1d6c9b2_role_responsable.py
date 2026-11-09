"""Ajoute un rôle dédié aux responsables légaux, séparé des apprenants."""

from typing import Sequence, Union

from alembic import op

revision: str = "k3f8a1d6c9b2"
down_revision: Union[str, Sequence[str], None] = "j8a4c2d7e9f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # PostgreSQL stocke les noms des membres de RoleUtilisateur.
    # La valeur ajoutée ne sera utilisée qu'après la fin de cette migration.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE roleutilisateur ADD VALUE IF NOT EXISTS 'RESPONSABLE'")


def downgrade() -> None:
    # PostgreSQL ne sait pas retirer une valeur d'un enum natif. On la laisse
    # disponible après downgrade : sans ligne ni code qui l'utilise, elle est
    # inoffensive et permet les downgrades contrôlés des révisions suivantes.
    return
