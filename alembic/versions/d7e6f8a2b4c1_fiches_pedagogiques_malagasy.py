"""Ajoute les fiches pédagogiques malagasy pour respecter la langue choisie."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e6f8a2b4c1"
down_revision: Union[str, None] = "c4f9a1b7d2e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("document"):
        raise RuntimeError("La table 'document' doit exister avant cette migration.")
    columns = {item["name"] for item in inspector.get_columns("document")}
    if "resume_ia_mg" not in columns:
        op.add_column("document", sa.Column("resume_ia_mg", sa.Text(), nullable=False, server_default=""))
    if "fiche_pedagogique_mg_json" not in columns:
        op.add_column("document", sa.Column("fiche_pedagogique_mg_json", sa.Text(), nullable=False, server_default="{}"))
    if "resume_statut_ia_mg" not in columns:
        op.add_column("document", sa.Column("resume_statut_ia_mg", sa.String(length=32), nullable=False, server_default="a_generer"))
    index_names = {item["name"] for item in sa.inspect(bind).get_indexes("document")}
    if "ix_document_resume_statut_ia_mg" not in index_names:
        op.create_index("ix_document_resume_statut_ia_mg", "document", ["resume_statut_ia_mg"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("document"):
        return
    index_names = {item["name"] for item in sa.inspect(bind).get_indexes("document")}
    if "ix_document_resume_statut_ia_mg" in index_names:
        op.drop_index("ix_document_resume_statut_ia_mg", table_name="document")
    columns = {item["name"] for item in sa.inspect(bind).get_columns("document")}
    to_drop = [name for name in ("resume_statut_ia_mg", "fiche_pedagogique_mg_json", "resume_ia_mg") if name in columns]
    if not to_drop:
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("document", recreate="always") as batch:
            for name in to_drop:
                batch.drop_column(name)
    else:
        for name in to_drop:
            op.drop_column("document", name)
