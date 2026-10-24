"""Garantit que les cibles scolaires, universitaires et transversales sont disjointes.

Revision ID: a7c3e91f5b24
Revises: f4a8c2d9e761
"""
from alembic import op
import sqlalchemy as sa

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


def _ensure_demande_scolaire_matiere_schema() -> None:
    """Répare le schéma préexistant où la portée scolaire avait été livrée sans matière.

    La migration de référentiel qui a introduit les autres cibles de demande
    avait déjà été appliquée dans certains environnements. Modifier cette
    migration historique ne met pas à jour ces bases : cette vérification
    complète donc la colonne, sa FK, son index et les index uniques partiels
    avec matière avant d'ajouter la contrainte qui les référence.
    """
    table = "demandecreationcercle"
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns(table)}
    foreign_keys = {
        foreign_key.get("name")
        for foreign_key in inspector.get_foreign_keys(table)
    }

    if "matiere_scolaire_id" not in columns:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("matiere_scolaire_id", sa.Integer(), nullable=True))
            if "fk_demandecercle_matiere_scolaire" not in foreign_keys:
                batch.create_foreign_key(
                    "fk_demandecercle_matiere_scolaire",
                    "matierescolaire",
                    ["matiere_scolaire_id"],
                    ["id"],
                )
    elif "fk_demandecercle_matiere_scolaire" not in foreign_keys:
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(
                "fk_demandecercle_matiere_scolaire",
                "matierescolaire",
                ["matiere_scolaire_id"],
                ["id"],
            )

    inspector = sa.inspect(bind)
    indexes = {
        index["name"]: index
        for index in inspector.get_indexes(table)
        if index.get("name")
    }
    index_name = "ix_demandecreationcercle_matiere_scolaire_id"
    if index_name not in indexes:
        op.create_index(index_name, table, ["matiere_scolaire_id"])

    # Les anciennes versions n'avaient que 4 permutations (classe/série/
    # établissement). La portée matière ajoute les 4 autres permutations et
    # doit aussi faire partie de la prédication des 4 indices existants.
    dimensions_optionnelles = [
        "option_scolaire_id",
        "etablissement_scolaire_id",
        "matiere_scolaire_id",
    ]
    for masque in range(8):
        colonnes = ["niveau_scolaire_id"] + [
            colonne for bit, colonne in enumerate(dimensions_optionnelles)
            if masque & (1 << bit)
        ]
        conditions = [
            "statut = 'EN_ATTENTE'",
            "portee_academique = 'scolaire'",
            "niveau_scolaire_id IS NOT NULL",
        ]
        conditions.extend(
            f"{colonne} IS {'NOT ' if masque & (1 << bit) else ''}NULL"
            for bit, colonne in enumerate(dimensions_optionnelles)
        )
        condition = " AND ".join(conditions)
        nom = f"ix_demande_creation_scolaire_unique_{masque:03b}"
        index = indexes.get(nom)
        options_dialecte = (index or {}).get("dialect_options") or {}
        ancienne_condition = options_dialecte.get("postgresql_where") or options_dialecte.get("sqlite_where")
        index_correct = (
            index is not None
            and index.get("column_names") == colonnes
            and "matiere_scolaire_id" in str(ancienne_condition)
        )
        if index_correct:
            continue
        if index is not None:
            op.drop_index(nom, table_name=table)
        op.create_index(
            nom,
            table,
            colonnes,
            unique=True,
            postgresql_where=sa.text(condition),
            sqlite_where=sa.text(condition),
        )
        indexes[nom] = {
            "name": nom,
            "column_names": colonnes,
            "dialect_options": {"postgresql_where": condition, "sqlite_where": condition},
        }


def upgrade() -> None:
    # Répare d'abord le schéma historique : sans cette étape, PostgreSQL ne
    # peut pas créer la contrainte de la table demandecreationcercle.
    _ensure_demande_scolaire_matiere_schema()

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
