"""double authentification (TOTP) et codes de secours

Revision ID: 6a1c8e4b7f30
Revises: 4f7a1d6e9c02
Create Date: 2026-08-11 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '6a1c8e4b7f30'
down_revision: Union[str, None] = '4f7a1d6e9c02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('utilisateur', sa.Column('totp_secret', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('utilisateur', sa.Column('totp_active', sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        'codesecours2fa',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('utilisateur_id', sa.Integer(), nullable=False),
        sa.Column('code_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('utilise', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.Column('date_utilisation', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateur.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('codesecours2fa')
    op.drop_column('utilisateur', 'totp_active')
    op.drop_column('utilisateur', 'totp_secret')
