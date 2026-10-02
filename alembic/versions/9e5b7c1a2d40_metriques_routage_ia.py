"""Metriques et routage adaptatif de l'ensemble IA."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9e5b7c1a2d40"
down_revision: Union[str, None] = "7c4d9e2a1f60"
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
        raise RuntimeError("La table 'tacheia' est absente avant la migration 9e5b7c1a2d40.")

    cols = _cols(inspector, "tacheia")
    for name, column in {
        "strategie_verification": sa.Column(
            "strategie_verification", sa.String(), nullable=False, server_default="standard"
        ),
        "score_risque": sa.Column(
            "score_risque", sa.Integer(), nullable=False, server_default="0"
        ),
    }.items():
        if name not in cols:
            op.add_column("tacheia", column)

    inspector = sa.inspect(bind)
    if "ix_tacheia_strategie_verification" not in _indexes(inspector, "tacheia"):
        op.create_index(
            "ix_tacheia_strategie_verification",
            "tacheia",
            ["strategie_verification"],
        )

    if not inspector.has_table("performancemodeleia"):
        op.create_table(
            "performancemodeleia",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("type_interaction", sa.String(), nullable=False),
            sa.Column("matiere", sa.String(), nullable=False, server_default=""),
            sa.Column("niveau", sa.String(), nullable=False, server_default=""),
            sa.Column("modele", sa.String(), nullable=False),
            sa.Column("strategie", sa.String(), nullable=False, server_default="standard"),
            sa.Column("appels", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("confiants", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("problemes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("arbitrages", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("derniere_duree_secondes", sa.Float(), nullable=True),
            sa.Column("duree_moyenne_secondes", sa.Float(), nullable=False, server_default="0"),
            sa.Column("premiere_utilisation_le", sa.DateTime(), nullable=False),
            sa.Column("derniere_utilisation_le", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "type_interaction",
                "matiere",
                "niveau",
                "modele",
                "strategie",
                name="uq_performance_modele_ia",
            ),
        )
    else:
        cols = _cols(inspector, "performancemodeleia")
        additions = {
            "id": sa.Column("id", sa.Integer(), nullable=True),
            "type_interaction": sa.Column("type_interaction", sa.String(), nullable=True),
            "matiere": sa.Column("matiere", sa.String(), nullable=True, server_default=""),
            "niveau": sa.Column("niveau", sa.String(), nullable=True, server_default=""),
            "modele": sa.Column("modele", sa.String(), nullable=True),
            "strategie": sa.Column("strategie", sa.String(), nullable=True, server_default="standard"),
            "appels": sa.Column("appels", sa.Integer(), nullable=True, server_default="0"),
            "confiants": sa.Column("confiants", sa.Integer(), nullable=True, server_default="0"),
            "problemes": sa.Column("problemes", sa.Integer(), nullable=True, server_default="0"),
            "arbitrages": sa.Column("arbitrages", sa.Integer(), nullable=True, server_default="0"),
            "derniere_duree_secondes": sa.Column("derniere_duree_secondes", sa.Float(), nullable=True),
            "duree_moyenne_secondes": sa.Column("duree_moyenne_secondes", sa.Float(), nullable=True, server_default="0"),
            "premiere_utilisation_le": sa.Column("premiere_utilisation_le", sa.DateTime(), nullable=True),
            "derniere_utilisation_le": sa.Column("derniere_utilisation_le", sa.DateTime(), nullable=True),
        }
        for name, column in additions.items():
            if name not in cols:
                op.add_column("performancemodeleia", column)

        inspector = sa.inspect(bind)
        unique_cols = (
            "type_interaction", "matiere", "niveau", "modele", "strategie"
        )
        uniques = inspector.get_unique_constraints("performancemodeleia")
        if not any(tuple(u.get("column_names") or ()) == unique_cols for u in uniques):
            op.create_unique_constraint(
                "uq_performance_modele_ia",
                "performancemodeleia",
                list(unique_cols),
            )

    inspector = sa.inspect(bind)
    indexes = _indexes(inspector, "performancemodeleia")
    targets = {
        "ix_performancemodeleia_type_interaction": ["type_interaction"],
        "ix_performancemodeleia_matiere": ["matiere"],
        "ix_performancemodeleia_niveau": ["niveau"],
        "ix_performancemodeleia_modele": ["modele"],
        "ix_performancemodeleia_strategie": ["strategie"],
        "ix_performance_modele_ia_lookup": [
            "type_interaction", "matiere", "niveau"
        ],
    }
    for name, cols in targets.items():
        if name not in indexes:
            op.create_index(name, "performancemodeleia", cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("performancemodeleia"):
        indexes = _indexes(inspector, "performancemodeleia")
        for name in (
            "ix_performance_modele_ia_lookup",
            "ix_performancemodeleia_strategie",
            "ix_performancemodeleia_modele",
            "ix_performancemodeleia_niveau",
            "ix_performancemodeleia_matiere",
            "ix_performancemodeleia_type_interaction",
        ):
            if name in indexes:
                op.drop_index(name, table_name="performancemodeleia")
        op.drop_table("performancemodeleia")

    inspector = sa.inspect(bind)
    if inspector.has_table("tacheia"):
        indexes = _indexes(inspector, "tacheia")
        if "ix_tacheia_strategie_verification" in indexes:
            op.drop_index(
                "ix_tacheia_strategie_verification",
                table_name="tacheia",
            )
        cols = _cols(inspector, "tacheia")
        if "score_risque" in cols:
            op.drop_column("tacheia", "score_risque")
        if "strategie_verification" in cols:
            op.drop_column("tacheia", "strategie_verification")
