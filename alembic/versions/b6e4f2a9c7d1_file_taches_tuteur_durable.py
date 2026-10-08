"""Etend la file IA durable aux verifications Tuteur."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6e4f2a9c7d1"
down_revision: Union[str, None] = "c9f1a7e4b3d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(inspector, table: str) -> set[str]:
    return {c["name"] for c in inspector.get_columns(table)}


def _indexes(inspector, table: str) -> set[str]:
    return {i["name"] for i in inspector.get_indexes(table) if i.get("name")}


def _unique_names(inspector, table: str) -> set[str]:
    return {
        u["name"]
        for u in inspector.get_unique_constraints(table)
        if u.get("name")
    }


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("tacheia"):
        raise RuntimeError(
            "La table 'tacheia' est absente alors que la file IA Tuteur "
            "depend de la migration 7c4d9e2a1f60."
        )

    cols = _cols(inspector, "tacheia")
    uniques = _unique_names(inspector, "tacheia")

    # SQLite ne sait pas modifier directement une colonne existante avec
    # ALTER COLUMN. Batch mode reconstruit la table en conservant les donnees
    # et les contraintes historiques tout en ajoutant la nouvelle reference.
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("tacheia", recreate="always") as batch:
            if "tentative_quiz_id" in cols:
                batch.alter_column(
                    "tentative_quiz_id",
                    existing_type=sa.Integer(),
                    nullable=True,
                )
            if "session_tuteur_id" not in cols:
                batch.add_column(
                    sa.Column("session_tuteur_id", sa.Integer(), nullable=True)
                )
            if "session_tuteur_id" not in cols:
                batch.create_foreign_key(
                    "fk_tacheia_session_tuteur",
                    "sessiontuteur",
                    ["session_tuteur_id"],
                    ["id"],
                )
            if "uq_tache_ia_type_session_tuteur" not in uniques:
                batch.create_unique_constraint(
                    "uq_tache_ia_type_session_tuteur",
                    ["type_tache", "session_tuteur_id"],
                )
    else:
        if "tentative_quiz_id" in cols:
            op.alter_column(
                "tacheia",
                "tentative_quiz_id",
                existing_type=sa.Integer(),
                nullable=True,
            )
        if "session_tuteur_id" not in cols:
            op.add_column(
                "tacheia",
                sa.Column("session_tuteur_id", sa.Integer(), nullable=True),
            )

        inspector = sa.inspect(bind)
        fks = inspector.get_foreign_keys("tacheia")
        fk_present = any(
            tuple(fk.get("constrained_columns") or ()) == ("session_tuteur_id",)
            and fk.get("referred_table") == "sessiontuteur"
            for fk in fks
        )
        if not fk_present:
            op.create_foreign_key(
                "fk_tacheia_session_tuteur",
                "tacheia",
                "sessiontuteur",
                ["session_tuteur_id"],
                ["id"],
            )

        inspector = sa.inspect(bind)
        uniques = _unique_names(inspector, "tacheia")
        if "uq_tache_ia_type_session_tuteur" not in uniques:
            op.create_unique_constraint(
                "uq_tache_ia_type_session_tuteur",
                "tacheia",
                ["type_tache", "session_tuteur_id"],
            )

    inspector = sa.inspect(bind)
    indexes = _indexes(inspector, "tacheia")
    if "ix_tacheia_session_tuteur_id" not in indexes:
        op.create_index(
            "ix_tacheia_session_tuteur_id",
            "tacheia",
            ["session_tuteur_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("tacheia"):
        return

    indexes = _indexes(inspector, "tacheia")
    if "ix_tacheia_session_tuteur_id" in indexes:
        op.drop_index("ix_tacheia_session_tuteur_id", table_name="tacheia")

    uniques = _unique_names(inspector, "tacheia")
    cols = _cols(inspector, "tacheia")

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("tacheia", recreate="always") as batch:
            if "uq_tache_ia_type_session_tuteur" in uniques:
                batch.drop_constraint("uq_tache_ia_type_session_tuteur", type_="unique")
            if "session_tuteur_id" in cols:
                batch.drop_constraint("fk_tacheia_session_tuteur", type_="foreignkey")
                batch.drop_column("session_tuteur_id")
            if "tentative_quiz_id" in cols:
                batch.alter_column(
                    "tentative_quiz_id",
                    existing_type=sa.Integer(),
                    nullable=False,
                )
    else:
        if "uq_tache_ia_type_session_tuteur" in uniques:
            op.drop_constraint(
                "uq_tache_ia_type_session_tuteur",
                "tacheia",
                type_="unique",
            )

        inspector = sa.inspect(bind)
        fks = inspector.get_foreign_keys("tacheia")
        if any(
            fk.get("name") == "fk_tacheia_session_tuteur"
            or (
                tuple(fk.get("constrained_columns") or ()) == ("session_tuteur_id",)
                and fk.get("referred_table") == "sessiontuteur"
            )
            for fk in fks
        ):
            op.drop_constraint(
                "fk_tacheia_session_tuteur",
                "tacheia",
                type_="foreignkey",
            )

        if "session_tuteur_id" in cols:
            op.drop_column("tacheia", "session_tuteur_id")
        if "tentative_quiz_id" in cols:
            op.alter_column(
                "tacheia",
                "tentative_quiz_id",
                existing_type=sa.Integer(),
                nullable=False,
            )
