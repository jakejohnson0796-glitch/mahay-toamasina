"""Ajoute les preuves persistantes de diversité pour confirmer la maîtrise."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f9b8d3a6c2e1"
down_revision: Union[str, None] = "f8a2c6e4b1d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("progressionnotion"):
        raise RuntimeError(
            "La table 'progressionnotion' doit exister avant d'ajouter les preuves de maîtrise."
        )

    colonnes = {column["name"] for column in inspector.get_columns("progressionnotion")}
    if "preuves_apprentissage_json" not in colonnes:
        op.add_column(
            "progressionnotion",
            sa.Column(
                "preuves_apprentissage_json",
                sa.String(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("progressionnotion"):
        return

    colonnes = {column["name"] for column in inspector.get_columns("progressionnotion")}
    if "preuves_apprentissage_json" not in colonnes:
        return

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("progressionnotion", recreate="always") as batch:
            batch.drop_column("preuves_apprentissage_json")
    else:
        op.drop_column("progressionnotion", "preuves_apprentissage_json")
