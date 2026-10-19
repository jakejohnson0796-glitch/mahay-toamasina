"""Add tutor hint and human-review metadata for pedagogical fiches."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f2a9c7d1e4b8"
down_revision: Union[str, None] = "a1c8d5f2e7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("sessiontuteur"):
        columns = {c["name"] for c in sa.inspect(bind).get_columns("sessiontuteur")}
        if "indice" not in columns:
            op.add_column("sessiontuteur", sa.Column("indice", sa.Text(), nullable=False, server_default=""))
    if inspector.has_table("document"):
        columns = {c["name"] for c in sa.inspect(bind).get_columns("document")}
        if "fiche_validation_statut" not in columns:
            op.add_column("document", sa.Column("fiche_validation_statut", sa.String(20), nullable=False, server_default="a_verifier"))
        if "fiche_validee_par_id" not in columns:
            op.add_column("document", sa.Column("fiche_validee_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True))
        if "fiche_validee_le" not in columns:
            op.add_column("document", sa.Column("fiche_validee_le", sa.DateTime(), nullable=True))
        indexes = {i["name"] for i in sa.inspect(bind).get_indexes("document")}
        if "ix_document_fiche_validation_statut" not in indexes:
            op.create_index("ix_document_fiche_validation_statut", "document", ["fiche_validation_statut"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("document"):
        indexes = {i["name"] for i in sa.inspect(bind).get_indexes("document")}
        if "ix_document_fiche_validation_statut" in indexes:
            op.drop_index("ix_document_fiche_validation_statut", table_name="document")
        columns = {c["name"] for c in sa.inspect(bind).get_columns("document")}
        for name in ("fiche_validee_le", "fiche_validee_par_id", "fiche_validation_statut"):
            if name in columns:
                op.drop_column("document", name)
    if inspector.has_table("sessiontuteur"):
        columns = {c["name"] for c in sa.inspect(bind).get_columns("sessiontuteur")}
        if "indice" in columns:
            op.drop_column("sessiontuteur", "indice")
