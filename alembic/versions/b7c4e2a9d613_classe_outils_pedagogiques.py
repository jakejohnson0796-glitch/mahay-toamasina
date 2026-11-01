"""Enrichit les cours, devoirs, barèmes et corrections pédagogiques."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c4e2a9d613"
down_revision: Union[str, None] = "fae1c2d3b4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _colonnes(bind, table: str) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        raise RuntimeError(f"La table '{table}' doit exister avant cette migration.")
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if "objectifs" not in _colonnes(bind, "cours"):
        op.add_column("cours", sa.Column("objectifs", sa.Text(), nullable=True))
    if "code_invitation" not in _colonnes(bind, "cours"):
        op.add_column("cours", sa.Column("code_invitation", sa.String(length=12), nullable=True))
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("cours")}
    if "ix_cours_code_invitation" not in indexes:
        op.create_index("ix_cours_code_invitation", "cours", ["code_invitation"], unique=True)

    devoir_columns = _colonnes(bind, "devoir")
    if "bareme" not in devoir_columns:
        op.add_column(
            "devoir",
            sa.Column("bareme", sa.Float(), nullable=False, server_default=sa.text("20.0")),
        )
    if "criteres_json" not in devoir_columns:
        op.add_column("devoir", sa.Column("criteres_json", sa.Text(), nullable=True))
    if "est_clos" not in devoir_columns:
        op.add_column(
            "devoir",
            sa.Column("est_clos", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "archive" not in devoir_columns:
        op.add_column(
            "devoir",
            sa.Column("archive", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    rendu_columns = _colonnes(bind, "rendu_devoir")
    if "details_correction_json" not in rendu_columns:
        op.add_column("rendu_devoir", sa.Column("details_correction_json", sa.Text(), nullable=True))
    if "correction_ia_json" not in rendu_columns:
        op.add_column("rendu_devoir", sa.Column("correction_ia_json", sa.Text(), nullable=True))

    devoir_indexes = {item["name"] for item in sa.inspect(bind).get_indexes("devoir")}
    if "ix_devoir_est_clos" not in devoir_indexes:
        op.create_index("ix_devoir_est_clos", "devoir", ["est_clos"], unique=False)
    if "ix_devoir_archive" not in devoir_indexes:
        op.create_index("ix_devoir_archive", "devoir", ["archive"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("rendu_devoir"):
        cols = _colonnes(bind, "rendu_devoir")
        for name in ("correction_ia_json", "details_correction_json"):
            if name in cols:
                op.drop_column("rendu_devoir", name)

    if inspector.has_table("devoir"):
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes("devoir")}
        for name in ("ix_devoir_archive", "ix_devoir_est_clos"):
            if name in indexes:
                op.drop_index(name, table_name="devoir")
        cols = _colonnes(bind, "devoir")
        for name in ("archive", "est_clos", "criteres_json", "bareme"):
            if name in cols:
                op.drop_column("devoir", name)

    if inspector.has_table("cours"):
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes("cours")}
        if "ix_cours_code_invitation" in indexes:
            op.drop_index("ix_cours_code_invitation", table_name="cours")
        cols = _colonnes(bind, "cours")
        for name in ("code_invitation", "objectifs"):
            if name in cols:
                op.drop_column("cours", name)
