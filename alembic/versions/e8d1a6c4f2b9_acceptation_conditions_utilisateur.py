"""Enregistrer la version et la date d'acceptation des conditions à l'inscription."""

from alembic import op
import sqlalchemy as sa


revision: str = "e8d1a6c4f2b9"
down_revision: str | None = "9a4f7d1c2e80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    colonnes = {col["name"] for col in sa.inspect(op.get_bind()).get_columns("utilisateur")}
    if "conditions_acceptees_le" not in colonnes:
        op.add_column(
            "utilisateur",
            sa.Column("conditions_acceptees_le", sa.DateTime(), nullable=True),
        )
    if "version_conditions_acceptees" not in colonnes:
        op.add_column(
            "utilisateur",
            sa.Column("version_conditions_acceptees", sa.String(length=32), nullable=True),
        )


def downgrade() -> None:
    colonnes = {col["name"] for col in sa.inspect(op.get_bind()).get_columns("utilisateur")}
    if "version_conditions_acceptees" in colonnes:
        op.drop_column("utilisateur", "version_conditions_acceptees")
    if "conditions_acceptees_le" in colonnes:
        op.drop_column("utilisateur", "conditions_acceptees_le")
