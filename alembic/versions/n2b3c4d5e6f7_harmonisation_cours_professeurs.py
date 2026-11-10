"""Ajoute le suivi collaboratif et les versions harmonisées des cours."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "n2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "m1e7b3c5d9a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Notification.type_notification peut être un enum natif PostgreSQL
    # selon le schéma déjà déployé. Ajouter la valeur uniquement si ce type
    # existe ; les bases où la colonne est un VARCHAR ne nécessitent rien.
    if bind.dialect.name == "postgresql":
        enum_exists = bind.execute(
            sa.text("SELECT 1 FROM pg_type WHERE typname = :name"),
            {"name": "typenotification"},
        ).scalar_one_or_none()
        if enum_exists is not None:
            with op.get_context().autocommit_block():
                op.execute(
                    "ALTER TYPE typenotification "
                    "ADD VALUE IF NOT EXISTS 'HARMONISATION_COURS'"
                )
    document_columns = {
        column["name"] for column in inspector.get_columns("document")
    }
    if "contenu_harmonise" not in document_columns:
        op.add_column(
            "document",
            sa.Column("contenu_harmonise", sa.String(length=100000), nullable=False, server_default=""),
        )
    if "version_harmonisee" not in document_columns:
        op.add_column(
            "document",
            sa.Column("version_harmonisee", sa.Integer(), nullable=False, server_default="0"),
        )
    if "date_mise_a_jour_harmonisee" not in document_columns:
        op.add_column(
            "document",
            sa.Column("date_mise_a_jour_harmonisee", sa.DateTime(), nullable=True),
        )
    if not inspector.has_table("demandemiseajourcours"):
        op.create_table(
            "demandemiseajourcours",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("document.id"), nullable=False),
            sa.Column("auteur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
            sa.Column("version_source", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("passage_concerne", sa.String(length=2000), nullable=False),
            sa.Column("contenu_actuel", sa.String(length=100000), nullable=False, server_default=""),
            sa.Column("contenu_propose", sa.String(length=100000), nullable=False),
            sa.Column("justification", sa.String(length=10000), nullable=False),
            sa.Column("source_justificative", sa.String(length=5000), nullable=False),
            sa.Column("impact_pedagogique", sa.String(length=5000), nullable=False),
            sa.Column("statut", sa.String(length=32), nullable=False, server_default="en_attente"),
            sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column("date_modification", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column("traite_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
            sa.Column("date_traitement", sa.DateTime(), nullable=True),
            sa.Column("motif_decision", sa.String(length=5000), nullable=False, server_default=""),
            sa.CheckConstraint(
                "statut IN ('en_attente', 'en_discussion', 'precisions_demandees', 'validee', 'refusee')",
                name="ck_demandemiseajourcours_statut",
            ),
        )
    index_names = {
        index["name"] for index in sa.inspect(bind).get_indexes("demandemiseajourcours")
    }
    for name, columns in (
        ("ix_demande_mise_a_jour_document", ["document_id"]),
        ("ix_demande_mise_a_jour_auteur", ["auteur_id"]),
        ("ix_demande_mise_a_jour_statut_date", ["statut", "date_creation"]),
    ):
        if name not in index_names:
            op.create_index(name, "demandemiseajourcours", columns, unique=False)

    if not sa.inspect(bind).has_table("echangedemandemiseajourcours"):
        op.create_table(
            "echangedemandemiseajourcours",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column(
                "demande_id",
                sa.Integer(),
                sa.ForeignKey("demandemiseajourcours.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("auteur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
            sa.Column("message", sa.String(length=5000), nullable=False),
            sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        )
    index_names = {
        index["name"] for index in sa.inspect(bind).get_indexes("echangedemandemiseajourcours")
    }
    for name, columns in (
        ("ix_echangedemandemiseajourcours_demande_id", ["demande_id"]),
        ("ix_echangedemandemiseajourcours_auteur_id", ["auteur_id"]),
        ("ix_echangedemandemiseajourcours_date_creation", ["date_creation"]),
    ):
        if name not in index_names:
            op.create_index(name, "echangedemandemiseajourcours", columns, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("echangedemandemiseajourcours"):
        op.drop_table("echangedemandemiseajourcours")
    if inspector.has_table("demandemiseajourcours"):
        op.drop_table("demandemiseajourcours")
    if not inspector.has_table("document"):
        return
    columns = {item["name"] for item in sa.inspect(bind).get_columns("document")}
    for name in ("date_mise_a_jour_harmonisee", "version_harmonisee", "contenu_harmonise"):
        if name in columns:
            op.drop_column("document", name)
