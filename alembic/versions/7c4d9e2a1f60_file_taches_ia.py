"""File durable pour les traitements IA hors chemin HTTP."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c4d9e2a1f60"
down_revision: Union[str, None] = "f8a2c6e4b1d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(inspector, table: str) -> set[str]:
    return {c["name"] for c in inspector.get_columns(table)}


def _indexes(inspector, table: str) -> set[str]:
    return {i["name"] for i in inspector.get_indexes(table) if i.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("tacheia"):
        op.create_table(
            "tacheia",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("type_tache", sa.String(), nullable=False),
            sa.Column("tentative_quiz_id", sa.Integer(), nullable=False),
            sa.Column("statut", sa.String(), nullable=False),
            sa.Column("nombre_essais", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("disponible_le", sa.DateTime(), nullable=False),
            sa.Column("prise_en_charge_le", sa.DateTime(), nullable=True),
            sa.Column("terminee_le", sa.DateTime(), nullable=True),
            sa.Column("derniere_erreur", sa.String(), nullable=True),
            sa.Column("date_creation", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["tentative_quiz_id"], ["tentativequiz.id"]),
            sa.UniqueConstraint(
                "type_tache",
                "tentative_quiz_id",
                name="uq_tache_ia_type_tentative",
            ),
        )
    else:
        cols = _cols(inspector, "tacheia")
        additions = {
            "id": sa.Column("id", sa.Integer(), nullable=True),
            "type_tache": sa.Column("type_tache", sa.String(), nullable=True),
            "tentative_quiz_id": sa.Column("tentative_quiz_id", sa.Integer(), nullable=True),
            "statut": sa.Column("statut", sa.String(), nullable=True),
            "nombre_essais": sa.Column("nombre_essais", sa.Integer(), nullable=True, server_default="0"),
            "disponible_le": sa.Column("disponible_le", sa.DateTime(), nullable=True),
            "prise_en_charge_le": sa.Column("prise_en_charge_le", sa.DateTime(), nullable=True),
            "terminee_le": sa.Column("terminee_le", sa.DateTime(), nullable=True),
            "derniere_erreur": sa.Column("derniere_erreur", sa.String(), nullable=True),
            "date_creation": sa.Column("date_creation", sa.DateTime(), nullable=True),
        }
        for name, column in additions.items():
            if name not in cols:
                op.add_column("tacheia", column)

        inspector = sa.inspect(bind)
        uniques = inspector.get_unique_constraints("tacheia")
        unique_cols = ("type_tache", "tentative_quiz_id")
        if not any(tuple(u.get("column_names") or ()) == unique_cols for u in uniques):
            op.create_unique_constraint(
                "uq_tache_ia_type_tentative",
                "tacheia",
                ["type_tache", "tentative_quiz_id"],
            )

    inspector = sa.inspect(bind)
    indexes = _indexes(inspector, "tacheia")
    targets = {
        "ix_tacheia_type_tache": ["type_tache"],
        "ix_tacheia_tentative_quiz_id": ["tentative_quiz_id"],
        "ix_tacheia_statut": ["statut"],
        "ix_tacheia_disponible_le": ["disponible_le"],
        "ix_tacheia_date_creation": ["date_creation"],
        "ix_tache_ia_file": ["statut", "disponible_le", "id"],
    }
    for name, cols in targets.items():
        if name not in indexes:
            op.create_index(name, "tacheia", cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("tacheia"):
        return

    indexes = _indexes(inspector, "tacheia")
    for name in (
        "ix_tache_ia_file",
        "ix_tacheia_date_creation",
        "ix_tacheia_disponible_le",
        "ix_tacheia_statut",
        "ix_tacheia_tentative_quiz_id",
        "ix_tacheia_type_tache",
    ):
        if name in indexes:
            op.drop_index(name, table_name="tacheia")

    op.drop_table("tacheia")
