"""Ajoute le suivi académique pondéré et le registre de présence validé."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "g2a7f5d9c1e3"
down_revision: Union[str, Sequence[str], None] = "b7c4e2a9d613"
branch_labels = None
depends_on = None

def _colonnes(bind, table: str) -> set[str]:
    if not sa.inspect(bind).has_table(table):
        raise RuntimeError(f"La table '{table}' doit exister avant cette migration.")
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}

def upgrade() -> None:
    bind = op.get_bind()
    cols = _colonnes(bind, "devoir")
    if "coefficient" not in cols:
        op.add_column("devoir", sa.Column("coefficient", sa.Float(), nullable=False, server_default=sa.text("1.0")))
    if "periode" not in cols:
        op.add_column("devoir", sa.Column("periode", sa.String(length=40), nullable=True))
    if "url_destination" not in _colonnes(bind, "notification"):
        op.add_column("notification", sa.Column("url_destination", sa.String(length=300), nullable=True))
    if not sa.inspect(bind).has_table("pointagepresence"):
        op.create_table(
            "pointagepresence",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("seance_id", sa.Integer(), sa.ForeignKey("seance.id"), nullable=False),
            sa.Column("utilisateur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
            sa.Column("statut", sa.String(length=24), nullable=False, server_default="a_renseigner"),
            sa.Column("justificatif", sa.String(length=1200), nullable=True),
            sa.Column("saisi_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
            sa.Column("date_maj", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.UniqueConstraint("seance_id", "utilisateur_id", name="uq_pointagepresence_seance_utilisateur"),
        )
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes("pointagepresence")}
    for name, cols in (
        ("ix_pointagepresence_seance_id", ["seance_id"]),
        ("ix_pointagepresence_utilisateur_id", ["utilisateur_id"]),
        ("ix_pointagepresence_utilisateur_statut", ["utilisateur_id", "statut"]),
    ):
        if name not in indexes:
            op.create_index(name, "pointagepresence", cols, unique=False)

def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("pointagepresence"):
        indexes = {i["name"] for i in inspector.get_indexes("pointagepresence")}
        for name in ("ix_pointagepresence_utilisateur_statut", "ix_pointagepresence_utilisateur_id", "ix_pointagepresence_seance_id"):
            if name in indexes:
                op.drop_index(name, table_name="pointagepresence")
        op.drop_table("pointagepresence")
    if inspector.has_table("notification") and "url_destination" in _colonnes(bind, "notification"):
        op.drop_column("notification", "url_destination")
    if inspector.has_table("devoir"):
        cols = _colonnes(bind, "devoir")
        if "periode" in cols:
            op.drop_column("devoir", "periode")
        if "coefficient" in cols:
            op.drop_column("devoir", "coefficient")
