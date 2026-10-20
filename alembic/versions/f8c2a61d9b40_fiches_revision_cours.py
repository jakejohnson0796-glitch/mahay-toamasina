"""Carnets de révision IA personnalisés par étudiant et séance.

Revision ID: f8c2a61d9b40
Revises: c4f9a1b7d2e6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8c2a61d9b40"
down_revision: Union[str, None] = "c4f9a1b7d2e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_TACHE_FICHE = "fk_tacheia_fiche_revision_cours_id_ficherevisioncours"


def _colonnes(bind, table: str) -> set[str]:
    return {colonne["name"] for colonne in sa.inspect(bind).get_columns(table)}


def _a_fk_fiche_revision(bind) -> bool:
    return any(
        fk.get("name") == FK_TACHE_FICHE
        or (
            fk.get("referred_table") == "ficherevisioncours"
            and "fiche_revision_cours_id" in (fk.get("constrained_columns") or [])
        )
        for fk in sa.inspect(bind).get_foreign_keys("tacheia")
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("ficherevisioncours"):
        op.create_table(
            "ficherevisioncours",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("cours_id", sa.Integer(), sa.ForeignKey("cours.id"), nullable=False),
            sa.Column("seance_id", sa.Integer(), sa.ForeignKey("seance.id"), nullable=False),
            sa.Column("utilisateur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
            sa.Column("statut", sa.String(length=24), nullable=False, server_default="EN_ATTENTE"),
            sa.Column("contenu_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("sources_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("erreur_generation", sa.Text(), nullable=True),
            sa.Column("version_generation", sa.String(length=24), nullable=False, server_default="v1"),
            sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column("date_modification", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column("date_generation", sa.DateTime(), nullable=True),
            sa.UniqueConstraint(
                "seance_id", "utilisateur_id",
                name="uq_ficherevision_seance_utilisateur",
            ),
        )

    index_fiche = {item["name"] for item in sa.inspect(bind).get_indexes("ficherevisioncours")}
    for nom, colonnes in (
        ("ix_ficherevisioncours_cours_id", ["cours_id"]),
        ("ix_ficherevisioncours_seance_id", ["seance_id"]),
        ("ix_ficherevisioncours_utilisateur_id", ["utilisateur_id"]),
        ("ix_ficherevisioncours_statut", ["statut"]),
        ("ix_ficherevision_cours_utilisateur", ["cours_id", "utilisateur_id"]),
    ):
        if nom not in index_fiche:
            op.create_index(nom, "ficherevisioncours", colonnes, unique=False)

    colonnes_tache = _colonnes(bind, "tacheia")
    if "fiche_revision_cours_id" not in colonnes_tache:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("tacheia", recreate="always") as batch:
                batch.add_column(sa.Column("fiche_revision_cours_id", sa.Integer(), nullable=True))
                batch.create_foreign_key(
                    FK_TACHE_FICHE,
                    "ficherevisioncours",
                    ["fiche_revision_cours_id"],
                    ["id"],
                )
        else:
            op.add_column("tacheia", sa.Column("fiche_revision_cours_id", sa.Integer(), nullable=True))
            op.create_foreign_key(
                FK_TACHE_FICHE,
                "tacheia",
                "ficherevisioncours",
                ["fiche_revision_cours_id"],
                ["id"],
            )
    elif not _a_fk_fiche_revision(bind):
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("tacheia", recreate="always") as batch:
                batch.create_foreign_key(
                    FK_TACHE_FICHE,
                    "ficherevisioncours",
                    ["fiche_revision_cours_id"],
                    ["id"],
                )
        else:
            op.create_foreign_key(
                FK_TACHE_FICHE,
                "tacheia",
                "ficherevisioncours",
                ["fiche_revision_cours_id"],
                ["id"],
            )

    index_tache = {item["name"] for item in sa.inspect(bind).get_indexes("tacheia")}
    if "ix_tacheia_fiche_revision_cours_id" not in index_tache:
        op.create_index(
            "ix_tacheia_fiche_revision_cours_id",
            "tacheia",
            ["fiche_revision_cours_id"],
            unique=False,
        )
    if "uq_tache_ia_type_fiche_revision_cours" not in index_tache:
        op.create_index(
            "uq_tache_ia_type_fiche_revision_cours",
            "tacheia",
            ["type_tache", "fiche_revision_cours_id"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("tacheia"):
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes("tacheia")}
        for name in ("uq_tache_ia_type_fiche_revision_cours", "ix_tacheia_fiche_revision_cours_id"):
            if name in indexes:
                op.drop_index(name, table_name="tacheia")

        if "fiche_revision_cours_id" in _colonnes(bind, "tacheia"):
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("tacheia", recreate="always") as batch:
                    if _a_fk_fiche_revision(bind):
                        batch.drop_constraint(FK_TACHE_FICHE, type_="foreignkey")
                    batch.drop_column("fiche_revision_cours_id")
            else:
                if _a_fk_fiche_revision(bind):
                    op.drop_constraint(FK_TACHE_FICHE, "tacheia", type_="foreignkey")
                op.drop_column("tacheia", "fiche_revision_cours_id")

    if inspector.has_table("ficherevisioncours"):
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes("ficherevisioncours")}
        for name in (
            "ix_ficherevision_cours_utilisateur",
            "ix_ficherevisioncours_statut",
            "ix_ficherevisioncours_utilisateur_id",
            "ix_ficherevisioncours_seance_id",
            "ix_ficherevisioncours_cours_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name="ficherevisioncours")
        op.drop_table("ficherevisioncours")
