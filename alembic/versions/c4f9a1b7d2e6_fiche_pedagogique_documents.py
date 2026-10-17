"""Ajoute les fiches pédagogiques IA aux documents et à la file durable."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4f9a1b7d2e6"
down_revision: Union[str, None] = "fae1c2d3b4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _colonnes(bind, table: str) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        raise RuntimeError(f"La table '{table}' doit exister avant cette migration.")
    return {item["name"] for item in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    colonnes_document = _colonnes(bind, "document")
    if "resume_ia" not in colonnes_document:
        op.add_column("document", sa.Column("resume_ia", sa.Text(), nullable=False, server_default=""))
    if "fiche_pedagogique_json" not in colonnes_document:
        op.add_column("document", sa.Column("fiche_pedagogique_json", sa.Text(), nullable=False, server_default="{}"))
    if "resume_statut_ia" not in colonnes_document:
        op.add_column("document", sa.Column("resume_statut_ia", sa.String(length=32), nullable=False, server_default="a_generer"))
    if "resume_genere_le" not in colonnes_document:
        op.add_column("document", sa.Column("resume_genere_le", sa.DateTime(), nullable=True))

    colonnes_taches = _colonnes(bind, "tacheia")
    if "document_id" not in colonnes_taches:
        op.add_column("tacheia", sa.Column("document_id", sa.Integer(), sa.ForeignKey("document.id"), nullable=True))

    index_document = {item["name"] for item in sa.inspect(bind).get_indexes("document")}
    if "ix_document_resume_statut_ia" not in index_document:
        op.create_index("ix_document_resume_statut_ia", "document", ["resume_statut_ia"], unique=False)

    index_taches = {item["name"] for item in sa.inspect(bind).get_indexes("tacheia")}
    if "ix_tacheia_document_id" not in index_taches:
        op.create_index("ix_tacheia_document_id", "tacheia", ["document_id"], unique=False)
    if "uq_tache_ia_type_document" not in index_taches:
        op.create_index("uq_tache_ia_type_document", "tacheia", ["type_tache", "document_id"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("tacheia"):
        index_names = {item["name"] for item in sa.inspect(bind).get_indexes("tacheia")}
        for name in ("uq_tache_ia_type_document", "ix_tacheia_document_id"):
            if name in index_names:
                op.drop_index(name, table_name="tacheia")
        if "document_id" in {item["name"] for item in sa.inspect(bind).get_columns("tacheia")}:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("tacheia", recreate="always") as batch:
                    batch.drop_column("document_id")
            else:
                op.drop_column("tacheia", "document_id")

    if inspector.has_table("document"):
        index_names = {item["name"] for item in sa.inspect(bind).get_indexes("document")}
        if "ix_document_resume_statut_ia" in index_names:
            op.drop_index("ix_document_resume_statut_ia", table_name="document")
        colonnes = {item["name"] for item in sa.inspect(bind).get_columns("document")}
        supprimer = [nom for nom in ("resume_genere_le", "resume_statut_ia", "fiche_pedagogique_json", "resume_ia") if nom in colonnes]
        if supprimer:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("document", recreate="always") as batch:
                    for nom in supprimer:
                        batch.drop_column(nom)
            else:
                for nom in supprimer:
                    op.drop_column("document", nom)
