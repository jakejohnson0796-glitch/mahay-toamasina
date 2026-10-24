"""Marque les cercles scolaires gérés par la synchronisation du référentiel.

Revision ID: f4a8c2d9e761
Revises: d8f41b2c6e90
"""
from alembic import op
import sqlalchemy as sa

revision = "f4a8c2d9e761"
down_revision = "d8f41b2c6e90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cercleetude",
        sa.Column(
            "synchronise_referentiel",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_cercleetude_synchronise_referentiel",
        "cercleetude",
        ["synchronise_referentiel"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cercleetude_synchronise_referentiel",
        table_name="cercleetude",
    )
    op.drop_column("cercleetude", "synchronise_referentiel")
