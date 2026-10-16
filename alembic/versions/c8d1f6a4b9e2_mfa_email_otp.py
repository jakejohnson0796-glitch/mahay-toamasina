"""Ajoute la MFA par code email à usage unique.

Revision ID: c8d1f6a4b9e2
Revises: b4c6d8e0f2a4, e8d1a6c4f2b9
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d1f6a4b9e2"
down_revision: Union[str, Sequence[str], None] = ("b4c6d8e0f2a4", "e8d1a6c4f2b9")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    colonnes_utilisateur = {
        colonne["name"] for colonne in inspector.get_columns("utilisateur")
    }
    if "email_otp_active" not in colonnes_utilisateur:
        op.add_column(
            "utilisateur",
            sa.Column(
                "email_otp_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    inspector = sa.inspect(bind)
    if not inspector.has_table("codeemail2fa"):
        op.create_table(
            "codeemail2fa",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("utilisateur_id", sa.Integer(), nullable=False),
            sa.Column("purpose", sa.String(length=20), nullable=False),
            sa.Column("code_hash", sa.String(), nullable=False),
            sa.Column("expire_le", sa.DateTime(), nullable=False),
            sa.Column(
                "utilise", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column(
                "date_creation",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("date_utilisation", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["utilisateur_id"], ["utilisateur.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    indexes = {
        index["name"]
        for index in inspector.get_indexes("codeemail2fa")
        if index.get("name")
    } if inspector.has_table("codeemail2fa") else set()
    if "ix_codeemail2fa_utilisateur_id" not in indexes:
        op.create_index(
            "ix_codeemail2fa_utilisateur_id",
            "codeemail2fa",
            ["utilisateur_id"],
        )
    if "ix_codeemail2fa_purpose" not in indexes:
        op.create_index(
            "ix_codeemail2fa_purpose",
            "codeemail2fa",
            ["purpose"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("codeemail2fa"):
        indexes = {
            index["name"]
            for index in inspector.get_indexes("codeemail2fa")
            if index.get("name")
        }
        if "ix_codeemail2fa_purpose" in indexes:
            op.drop_index("ix_codeemail2fa_purpose", table_name="codeemail2fa")
        if "ix_codeemail2fa_utilisateur_id" in indexes:
            op.drop_index("ix_codeemail2fa_utilisateur_id", table_name="codeemail2fa")
        op.drop_table("codeemail2fa")

    colonnes = {
        colonne["name"] for colonne in sa.inspect(bind).get_columns("utilisateur")
    }
    if "email_otp_active" in colonnes:
        op.drop_column("utilisateur", "email_otp_active")
