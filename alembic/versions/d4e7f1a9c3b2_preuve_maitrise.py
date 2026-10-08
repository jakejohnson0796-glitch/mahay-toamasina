"""Ajoute la preuve de maitrise au parcours d'apprentissage."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e7f1a9c3b2"
down_revision: Union[str, None] = "b6e4f2a9c7d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("progressionnotion", recreate="always") as batch:
            batch.add_column(
                sa.Column("niveau_max_reussi", sa.String(), nullable=True)
            )
            batch.add_column(
                sa.Column(
                    "confiance_maitrise",
                    sa.Integer(),
                    nullable=False,
                    server_default=sa.text("0"),
                )
            )
            batch.add_column(
                sa.Column(
                    "maitrise_confirmee",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("0"),
                )
            )
            batch.add_column(sa.Column("derniere_preuve_le", sa.DateTime(), nullable=True))
            batch.add_column(sa.Column("prochaine_preuve_le", sa.DateTime(), nullable=True))
            batch.create_index(
                "ix_progressionnotion_maitrise_confirmee",
                ["maitrise_confirmee"],
            )
        return

    op.add_column(
        "progressionnotion",
        sa.Column("niveau_max_reussi", sa.String(), nullable=True),
    )
    op.add_column(
        "progressionnotion",
        sa.Column(
            "confiance_maitrise",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "progressionnotion",
        sa.Column(
            "maitrise_confirmee",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "progressionnotion",
        sa.Column("derniere_preuve_le", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "progressionnotion",
        sa.Column("prochaine_preuve_le", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_progressionnotion_maitrise_confirmee",
        "progressionnotion",
        ["maitrise_confirmee"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("progressionnotion", recreate="always") as batch:
            batch.drop_index("ix_progressionnotion_maitrise_confirmee")
            batch.drop_column("prochaine_preuve_le")
            batch.drop_column("derniere_preuve_le")
            batch.drop_column("maitrise_confirmee")
            batch.drop_column("confiance_maitrise")
            batch.drop_column("niveau_max_reussi")
        return

    op.drop_index("ix_progressionnotion_maitrise_confirmee", table_name="progressionnotion")
    op.drop_column("prochaine_preuve_le", "progressionnotion")
    op.drop_column("derniere_preuve_le", "progressionnotion")
    op.drop_column("maitrise_confirmee", "progressionnotion")
    op.drop_column("confiance_maitrise", "progressionnotion")
    op.drop_column("niveau_max_reussi", "progressionnotion")
