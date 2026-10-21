"""Fiche de révision automatique pour chaque document de cours approuvé.

Revision ID: a7c9e2f41d60
Revises: f8c2a61d9b40
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c9e2f41d60"
down_revision: Union[str, None] = "f8c2a61d9b40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_TACHE_FICHE_DOCUMENT = "fk_tacheia_fiche_revision_document_id_ficherevisiondocument"


def _colonnes(bind, table: str) -> set[str]:
    return {colonne["name"] for colonne in sa.inspect(bind).get_columns(table)}


def _a_fk_fiche_document(bind) -> bool:
    return any(
        fk.get("name") == FK_TACHE_FICHE_DOCUMENT
        or (
            fk.get("referred_table") == "ficherevisiondocument"
            and "fiche_revision_document_id" in (fk.get("constrained_columns") or [])
        )
        for fk in sa.inspect(bind).get_foreign_keys("tacheia")
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("ficherevisiondocument"):
        op.create_table(
            "ficherevisiondocument",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("document.id"), nullable=False),
            sa.Column("statut", sa.String(length=24), nullable=False, server_default="EN_ATTENTE"),
            sa.Column("contenu_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("sources_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("erreur_generation", sa.Text(), nullable=True),
            sa.Column("version_generation", sa.String(length=24), nullable=False, server_default="v1"),
            sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column("date_modification", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column("date_generation", sa.DateTime(), nullable=True),
        )

    indexes_fiche = {item["name"] for item in sa.inspect(bind).get_indexes("ficherevisiondocument")}
    for name, columns, unique in (
        ("ix_ficherevisiondocument_statut", ["statut"], False),
        ("uq_ficherevisiondocument_document", ["document_id"], True),
    ):
        if name not in indexes_fiche:
            op.create_index(name, "ficherevisiondocument", columns, unique=unique)

    colonnes_tache = _colonnes(bind, "tacheia")
    if "fiche_revision_document_id" not in colonnes_tache:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("tacheia", recreate="always") as batch:
                batch.add_column(sa.Column("fiche_revision_document_id", sa.Integer(), nullable=True))
                batch.create_foreign_key(
                    FK_TACHE_FICHE_DOCUMENT,
                    "ficherevisiondocument",
                    ["fiche_revision_document_id"],
                    ["id"],
                )
        else:
            op.add_column("tacheia", sa.Column("fiche_revision_document_id", sa.Integer(), nullable=True))
            op.create_foreign_key(
                FK_TACHE_FICHE_DOCUMENT,
                "tacheia",
                "ficherevisiondocument",
                ["fiche_revision_document_id"],
                ["id"],
            )
    elif not _a_fk_fiche_document(bind):
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("tacheia", recreate="always") as batch:
                batch.create_foreign_key(
                    FK_TACHE_FICHE_DOCUMENT,
                    "ficherevisiondocument",
                    ["fiche_revision_document_id"],
                    ["id"],
                )
        else:
            op.create_foreign_key(
                FK_TACHE_FICHE_DOCUMENT,
                "tacheia",
                "ficherevisiondocument",
                ["fiche_revision_document_id"],
                ["id"],
            )

    indexes_tache = {item["name"] for item in sa.inspect(bind).get_indexes("tacheia")}
    if "ix_tacheia_fiche_revision_document_id" not in indexes_tache:
        op.create_index(
            "ix_tacheia_fiche_revision_document_id",
            "tacheia",
            ["fiche_revision_document_id"],
            unique=False,
        )
    if "uq_tache_ia_type_fiche_revision_document" not in indexes_tache:
        op.create_index(
            "uq_tache_ia_type_fiche_revision_document",
            "tacheia",
            ["type_tache", "fiche_revision_document_id"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("tacheia"):
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes("tacheia")}
        for name in (
            "uq_tache_ia_type_fiche_revision_document",
            "ix_tacheia_fiche_revision_document_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name="tacheia")

        if "fiche_revision_document_id" in _colonnes(bind, "tacheia"):
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("tacheia", recreate="always") as batch:
                    if _a_fk_fiche_document(bind):
                        batch.drop_constraint(FK_TACHE_FICHE_DOCUMENT, type_="foreignkey")
                    batch.drop_column("fiche_revision_document_id")
            else:
                if _a_fk_fiche_document(bind):
                    op.drop_constraint(FK_TACHE_FICHE_DOCUMENT, "tacheia", type_="foreignkey")
                op.drop_column("fiche_revision_document_id")

    if inspector.has_table("ficherevisiondocument"):
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes("ficherevisiondocument")}
        for name in ("uq_ficherevisiondocument_document", "ix_ficherevisiondocument_statut"):
            if name in indexes:
                op.drop_index(name, table_name="ficherevisiondocument")
        op.drop_table("ficherevisiondocument")
