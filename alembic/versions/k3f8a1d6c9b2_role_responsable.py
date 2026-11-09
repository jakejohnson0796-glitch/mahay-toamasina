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
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # PostgreSQL ne permet pas de retirer une valeur d'un enum natif sans
    # recréer le type et migrer toutes ses colonnes. Le rollback doit être
    # réalisé explicitement après réaffectation des comptes RESPONSABLE.
    raise NotImplementedError(
        "PostgreSQL ne permet pas de supprimer directement une valeur enum. "
        "Réaffecter les comptes RESPONSABLE puis recréer roleutilisateur manuellement."
    )
