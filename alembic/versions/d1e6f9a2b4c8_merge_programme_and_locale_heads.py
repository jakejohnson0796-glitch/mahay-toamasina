"""Merge the official-programme and selected-locale migration branches."""
from typing import Sequence, Union

from alembic import op


revision: str = "d1e6f9a2b4c8"
down_revision: Union[str, Sequence[str], None] = (
    "a4b8c2d6e9f1",
    "c8d5f4a1b2e9",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Schema changes are applied by both parent branches.
    pass


def downgrade() -> None:
    # Keep both parent branches as independent rollback paths.
    pass
