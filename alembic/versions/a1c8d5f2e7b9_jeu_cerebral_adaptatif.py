"""Persiste les sessions du jeu cérébral adaptatif."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1c8d5f2e7b9"
down_revision: Union[str, None] = "d7e6f8a2b4c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "jeucerebralsession"
INDEX_USER_DATE = "ix_jeu_cerebral_user_date"
INDEX_DATE = "ix_jeucerebralsession_date_creation"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("utilisateur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
            sa.Column("theme_id", sa.String(length=40), nullable=False),
            sa.Column("langue", sa.String(length=5), nullable=False, server_default="fr"),
            sa.Column("source_generation", sa.String(length=16), nullable=False, server_default="ia"),
            sa.Column("difficulte_initiale", sa.String(length=16), nullable=False, server_default="Moyen"),
            sa.Column("nb_questions", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("questions_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("reponses_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("score", sa.Integer(), nullable=True),
            sa.Column("bonnes_reponses", sa.Integer(), nullable=True),
            sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("date_fin", sa.DateTime(), nullable=True),
            sa.Column("recommandation_json", sa.Text(), nullable=False, server_default="{}"),
        )
    index_names = {item["name"] for item in sa.inspect(bind).get_indexes(TABLE)}
    if INDEX_USER_DATE not in index_names:
        op.create_index(
            INDEX_USER_DATE,
            TABLE,
            ["utilisateur_id", "date_creation"],
            unique=False,
        )
    if INDEX_DATE not in index_names:
        op.create_index(INDEX_DATE, TABLE, ["date_creation"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        return
    indexes = {item["name"] for item in inspector.get_indexes(TABLE)}
    for name in (INDEX_USER_DATE, INDEX_DATE):
        if name in indexes:
            op.drop_index(name, table_name=TABLE)
    op.drop_table(TABLE)
