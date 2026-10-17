"""Ajoute les fiches pédagogiques IA aux documents et à la file durable."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4f9a1b7d2e6"
down_revision: Union[str, None] = "fae1c2d3b4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOM_FK_DOCUMENT_TACHE = "fk_tacheia_document_id_document"


def _colonnes(bind, table: str) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        raise RuntimeError(f"La table '{table}' doit exister avant cette migration.")
    return {item["name"] for item in inspector.get_columns(table)}


def _a_fk_document(bind) -> bool:
    return any(
        NOM_FK_DOCUMENT_TACHE == foreign_key.get("name")
        or (
            foreign_key.get("referred_table") == "document"
            and "document_id" in (foreign_key.get("constrained_columns") or [])
        )
        for foreign_key in sa.inspect(bind).get_foreign_keys("tacheia")
    )


def upgrade() -> None:
    bind = op.get_bind()
    colonnes_document = _colonnes(bind, "document")
    if "resume_ia" not in colonnes_document:
        op.add_column(
            "document",
            sa.Column("resume_ia", sa.Text(), nullable=False, server_default=""),
        )
    if "fiche_pedagogique_json" not in colonnes_document:
        op.add_column(
            "document",
            sa.Column("fiche_pedagogique_json", sa.Text(), nullable=False, server_default="{}"),
        )
    if "resume_statut_ia" not in colonnes_document:
        op.add_column(
            "document",
            sa.Column("resume_statut_ia", sa.String(length=32), nullable=False, server_default="a_generer"),
        )
    if "resume_genere_le" not in colonnes_document:
        op.add_column("document", sa.Column("resume_genere_le", sa.DateTime(), nullable=True))

    colonnes_taches = _colonnes(bind, "tacheia")
    if "document_id" not in colonnes_taches:
        if bind.dialect.name == "sqlite":
            # SQLite ne permet pas d'ajouter une FK par ALTER COLUMN :
            # Alembic reconstruit la table en mode batch.
            with op.batch_alter_table("tacheia", recreate="always") as batch:
                batch.add_column(sa.Column("document_id", sa.Integer(), nullable=True))
                batch.create_foreign_key(
                    NOM_FK_DOCUMENT_TACHE,
                    "document",
                    ["document_id"],
                    ["id"],
                )
        else:
            op.add_column("tacheia", sa.Column("document_id", sa.Integer(), nullable=True))
            op.create_foreign_key(
                NOM_FK_DOCUMENT_TACHE,
                "tacheia",
                "document",
                ["document_id"],
                ["id"],
            )
    elif not _a_fk_document(bind):
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("tacheia", recreate="always") as batch:
                batch.create_foreign_key(
                    NOM_FK_DOCUMENT_TACHE,
                    "document",
                    ["document_id"],
                    ["id"],
                )
        else:
            op.create_foreign_key(
                NOM_FK_DOCUMENT_TACHE,
                "tacheia",
                "document",
                ["document_id"],
                ["id"],
            )

    index_document = {item["name"] for item in sa.inspect(bind).get_indexes("document")}
    if "ix_document_resume_statut_ia" not in index_document:
        op.create_index(
            "ix_document_resume_statut_ia",
            "document",
            ["resume_statut_ia"],
            unique=False,
        )

    index_taches = {item["name"] for item in sa.inspect(bind).get_indexes("tacheia")}
    if "ix_tacheia_document_id" not in index_taches:
        op.create_index("ix_tacheia_document_id", "tacheia", ["document_id"], unique=False)
    if "uq_tache_ia_type_document" not in index_taches:
        op.create_index(
            "uq_tache_ia_type_document",
            "tacheia",
            ["type_tache", "document_id"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("tacheia"):
        index_names = {item["name"] for item in sa.inspect(bind).get_indexes("tacheia")}
        for name in ("uq_tache_ia_type_document", "ix_tacheia_document_id"):
            if name in index_names:
                op.drop_index(name, table_name="tacheia")

        colonnes_taches = {item["name"] for item in sa.inspect(bind).get_columns("tacheia")}
        if "document_id" in colonnes_taches:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("tacheia", recreate="always") as batch:
                    if _a_fk_document(bind):
                        batch.drop_constraint(NOM_FK_DOCUMENT_TACHE, type_="foreignkey")
                    batch.drop_column("document_id")
            else:
                if _a_fk_document(bind):
                    op.drop_constraint(NOM_FK_DOCUMENT_TACHE, "tacheia", type_="foreignkey")
                op.drop_column("tacheia", "document_id")

    if inspector.has_table("document"):
        index_names = {item["name"] for item in sa.inspect(bind).get_indexes("document")}
        if "ix_document_resume_statut_ia" in index_names:
            op.drop_index("ix_document_resume_statut_ia", table_name="document")
        colonnes = {item["name"] for item in sa.inspect(bind).get_columns("document")}
        supprimer = [
            nom for nom in ("resume_genere_le", "resume_statut_ia", "fiche_pedagogique_json", "resume_ia")
            if nom in colonnes
        ]
        if supprimer:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("document", recreate="always") as batch:
                    for nom in supprimer:
                        batch.drop_column(nom)
            else:
                for nom in supprimer:
                    op.drop_column("document", nom)
