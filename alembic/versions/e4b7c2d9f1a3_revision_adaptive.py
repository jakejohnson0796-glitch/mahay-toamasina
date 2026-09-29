"""Score de maitrise et revision espacee par notion."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4b7c2d9f1a3"
down_revision: Union[str, None] = "c8f4a1b7e2d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "progressionnotion",
        sa.Column("score_maitrise", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "progressionnotion",
        sa.Column("serie_reussites", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "progressionnotion",
        sa.Column("nb_revisions", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "progressionnotion",
        sa.Column("prochaine_revision_le", sa.DateTime(), nullable=True),
    )

    # Reconstitue une premiere estimation a partir de l'historique deja
    # disponible, afin que les comptes existants beneficient immediatement
    # du plan adaptatif sans devoir refaire tous leurs anciens quiz.
    op.execute(
        sa.text(
            """
            UPDATE progressionnotion
            SET score_maitrise = CASE
                WHEN nb_questions > 0
                THEN CAST((nb_reussites * 100) / nb_questions AS INTEGER)
                ELSE 0
            END
            """
        )
    )


def downgrade() -> None:
    op.drop_column("progressionnotion", "prochaine_revision_le")
    op.drop_column("progressionnotion", "nb_revisions")
    op.drop_column("progressionnotion", "serie_reussites")
    op.drop_column("progressionnotion", "score_maitrise")
