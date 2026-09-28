"""Progression d'apprentissage par notion et contexte Tuteur IA."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8f4a1b7e2d9"
down_revision: Union[str, None] = "a91c7e4d2b6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "progressionnotion",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("utilisateur_id", sa.Integer(), nullable=False),
        sa.Column("matiere", sa.String(), nullable=False),
        sa.Column("notion", sa.String(), nullable=False),
        sa.Column("niveau", sa.String(), nullable=True),
        sa.Column("nb_questions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nb_reussites", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nb_erreurs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("derniere_erreur_le", sa.DateTime(), nullable=True),
        sa.Column("derniere_reussite_le", sa.DateTime(), nullable=True),
        sa.Column("date_maj", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["utilisateur_id"], ["utilisateur.id"]),
        sa.UniqueConstraint(
            "utilisateur_id",
            "matiere",
            "notion",
            name="uq_progression_notion_utilisateur_matiere_notion",
        ),
    )
    op.create_index(
        "ix_progressionnotion_utilisateur_id",
        "progressionnotion",
        ["utilisateur_id"],
    )
    op.create_index(
        "ix_progressionnotion_matiere",
        "progressionnotion",
        ["matiere"],
    )
    op.create_index(
        "ix_progressionnotion_notion",
        "progressionnotion",
        ["notion"],
    )
    op.create_index(
        "ix_progression_notion_utilisateur_score",
        "progressionnotion",
        ["utilisateur_id", "nb_erreurs", "nb_reussites"],
    )

    op.add_column("sessiontuteur", sa.Column("notion", sa.String(), nullable=True))
    op.add_column("sessiontuteur", sa.Column("progression_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_sessiontuteur_progression_notion",
        "sessiontuteur",
        "progressionnotion",
        ["progression_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_sessiontuteur_progression_notion", "sessiontuteur", type_="foreignkey")
    op.drop_column("sessiontuteur", "progression_id")
    op.drop_column("sessiontuteur", "notion")
    op.drop_index("ix_progression_notion_utilisateur_score", table_name="progressionnotion")
    op.drop_index("ix_progressionnotion_notion", table_name="progressionnotion")
    op.drop_index("ix_progressionnotion_matiere", table_name="progressionnotion")
    op.drop_index("ix_progressionnotion_utilisateur_id", table_name="progressionnotion")
    op.drop_table("progressionnotion")
