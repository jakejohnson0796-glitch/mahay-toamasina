"""Ajoute les preuves persistantes de maîtrise et les sources du Tuteur."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f9b8d3a6c2e1"
down_revision: Union[str, None] = "f8a2c6e4b1d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _colonnes(bind, table: str) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        raise RuntimeError(f"La table '{table}' doit exister avant cette migration.")
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # Colonnes additives et idempotentes : aucune ligne historique n'est supprimée.
    if "preuves_apprentissage_json" not in _colonnes(bind, "progressionnotion"):
        op.add_column(
            "progressionnotion",
            sa.Column(
                "preuves_apprentissage_json",
                sa.String(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )

    if "sources_documentaires_json" not in _colonnes(bind, "sessiontuteur"):
        op.add_column(
            "sessiontuteur",
            sa.Column(
                "sources_documentaires_json",
                sa.String(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
        )

    # Une ancienne confirmation sans empreinte de questions distinctes ne
    # constitue pas une preuve suffisante : on la remet en attente de validation.
    op.execute(
        sa.text(
            """
            UPDATE progressionnotion
            SET maitrise_confirmee = :non_confirmee
            WHERE maitrise_confirmee = :confirmee
              AND (
                preuves_apprentissage_json IS NULL
                OR preuves_apprentissage_json = '{}'
                OR preuves_apprentissage_json = ''
              )
            """
        ).bindparams(non_confirmee=False, confirmee=True)
    )


def downgrade() -> None:
    bind = op.get_bind()

    for table, column in (
        ("sessiontuteur", "sources_documentaires_json"),
        ("progressionnotion", "preuves_apprentissage_json"),
    ):
        inspector = sa.inspect(bind)
        if not inspector.has_table(table):
            continue
        columns = {item["name"] for item in inspector.get_columns(table)}
        if column not in columns:
            continue
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table(table, recreate="always") as batch:
                batch.drop_column(column)
        else:
            op.drop_column(table, column)
