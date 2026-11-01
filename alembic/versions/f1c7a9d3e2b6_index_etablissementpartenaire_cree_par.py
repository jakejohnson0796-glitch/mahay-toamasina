"""Indexe la FK de création des établissements partenaires.

La colonne cree_par_id a été ajoutée avec la table institutionnelle après
la migration générale des index de clés étrangères. Cet index couvre les
jointures et les suppressions référentielles futures.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "f1c7a9d3e2b6"
down_revision = "e2b7c9d4a1f6"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_etablissementpartenaire_cree_par_id"
TABLE_NAME = "etablissementpartenaire"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE_NAME):
        return
    indexes = {item["name"] for item in inspector.get_indexes(TABLE_NAME)}
    if INDEX_NAME not in indexes:
        op.create_index(INDEX_NAME, TABLE_NAME, ["cree_par_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(TABLE_NAME):
        indexes = {item["name"] for item in inspector.get_indexes(TABLE_NAME)}
        if INDEX_NAME in indexes:
            op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
