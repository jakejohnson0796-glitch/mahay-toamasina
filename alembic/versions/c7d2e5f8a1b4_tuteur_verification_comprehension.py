"""Persist learner understanding checks before unlocking tutor exercises."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c7d2e5f8a1b4"
down_revision: Union[str, None] = "f2a9c7d1e4b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("sessiontuteur"):
        return
    columns = {column["name"] for column in sa.inspect(bind).get_columns("sessiontuteur")}
    if "comprehension_validee" not in columns:
        op.add_column(
            "sessiontuteur",
            sa.Column("comprehension_validee", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "comprehension_reponse" not in columns:
        op.add_column(
            "sessiontuteur",
            sa.Column("comprehension_reponse", sa.Text(), nullable=False, server_default=""),
        )
    if "comprehension_feedback" not in columns:
        op.add_column(
            "sessiontuteur",
            sa.Column("comprehension_feedback", sa.Text(), nullable=False, server_default=""),
        )
    if "comprehension_indice" not in columns:
        op.add_column(
            "sessiontuteur",
            sa.Column("comprehension_indice", sa.Text(), nullable=False, server_default=""),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("sessiontuteur"):
        return
    columns = {column["name"] for column in sa.inspect(bind).get_columns("sessiontuteur")}
    for name in (
        "comprehension_indice",
        "comprehension_feedback",
        "comprehension_reponse",
        "comprehension_validee",
    ):
        if name in columns:
            op.drop_column("sessiontuteur", name)
