"""Remember the selected language for personal course revision sheets."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c8d5f4a1b2e9"
down_revision: Union[str, Sequence[str], None] = "b7c3e9a1d5f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ficherevisioncours",
        sa.Column("langue", sa.String(length=5), nullable=False, server_default="fr"),
    )
    op.create_index("ix_ficherevisioncours_langue", "ficherevisioncours", ["langue"])


def downgrade() -> None:
    op.drop_index("ix_ficherevisioncours_langue", table_name="ficherevisioncours")
    op.drop_column("ficherevisioncours", "langue")
