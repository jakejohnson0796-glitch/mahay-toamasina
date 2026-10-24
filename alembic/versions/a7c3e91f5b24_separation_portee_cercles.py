"""Garantit que les cibles scolaires, universitaires et transversales sont disjointes.

Revision ID: a7c3e91f5b24
Revises: f4a8c2d9e761
"""
from alembic import op

revision = "a7c3e91f5b24"
down_revision = "f4a8c2d9e761"
branch_labels = None
depends_on = None


_CONDITION_CERCLE = (
    "(portee_academique = 'scolaire' AND mention_id IS NULL "
    "AND filiere_id IS NULL AND niveau IS NULL AND niveau_scolaire_id IS NOT NULL) OR "
    "(portee_academique = 'universitaire' AND niveau_scolaire_id IS NULL "
    "AND option_scolaire_id IS NULL AND etablissement_scolaire_id IS NULL "
    "AND matiere_scolaire_id IS NULL) OR "
    "(portee_academique = 'transversal' AND mention_id IS NULL "
    "AND filiere_id IS NULL AND niveau IS NULL AND niveau_scolaire_id IS NULL "
    "AND option_scolaire_id IS NULL AND etablissement_scolaire_id IS NULL "
    "AND matiere_scolaire_id IS NULL)"
)


def upgrade() -> None:
    # Batch mode maintient la compatibilité SQLite (tests locaux) tout en
    # utilisant un ALTER TABLE classique sur PostgreSQL en production.
    with op.batch_alter_table("cercleetude") as batch:
        batch.create_check_constraint(
            "ck_cercle_portee_cible_separee",
            _CONDITION_CERCLE,
        )
    with op.batch_alter_table("demandecreationcercle") as batch:
        batch.create_check_constraint(
            "ck_demandecreationcercle_portee_cible_separee",
            _CONDITION_CERCLE,
        )


def downgrade() -> None:
    with op.batch_alter_table("demandecreationcercle") as batch:
        batch.drop_constraint(
            "ck_demandecreationcercle_portee_cible_separee",
            type_="check",
        )
    with op.batch_alter_table("cercleetude") as batch:
        batch.drop_constraint(
            "ck_cercle_portee_cible_separee",
            type_="check",
        )
