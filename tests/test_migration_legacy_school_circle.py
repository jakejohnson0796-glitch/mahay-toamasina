"""Régression pour les bases qui avaient déjà la portée scolaire sans matière sur les demandes."""
import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "a7c3e91f5b24_separation_portee_cercles.py"
)


def _charger_migration():
    spec = importlib.util.spec_from_file_location("migration_portee_cercles", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_repare_une_table_de_demande_existante_sans_matiere():
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE matierescolaire (id INTEGER PRIMARY KEY)"
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE cercleetude (
                    id INTEGER PRIMARY KEY,
                    portee_academique VARCHAR(20) NOT NULL,
                    mention_id INTEGER,
                    filiere_id INTEGER,
                    niveau VARCHAR(40),
                    niveau_scolaire_id INTEGER,
                    option_scolaire_id INTEGER,
                    etablissement_scolaire_id INTEGER,
                    matiere_scolaire_id INTEGER,
                    statut VARCHAR(20) NOT NULL DEFAULT 'ACTIF'
                )
                """
            )
            # Représente l'ancien schéma en production : les autres dimensions
            # scolaires existent, mais pas encore la colonne matière.
            connection.exec_driver_sql(
                """
                CREATE TABLE demandecreationcercle (
                    id INTEGER PRIMARY KEY,
                    utilisateur_id INTEGER NOT NULL,
                    portee_academique VARCHAR(20) NOT NULL DEFAULT 'universitaire',
                    mention_id INTEGER,
                    filiere_id INTEGER,
                    niveau VARCHAR(40),
                    niveau_scolaire_id INTEGER,
                    option_scolaire_id INTEGER,
                    etablissement_scolaire_id INTEGER,
                    nom VARCHAR(180) NOT NULL,
                    description VARCHAR(500),
                    raison VARCHAR(1000) NOT NULL,
                    statut VARCHAR(30) NOT NULL DEFAULT 'EN_ATTENTE',
                    date_creation TIMESTAMP
                )
                """
            )
            connection.exec_driver_sql(
                "INSERT INTO cercleetude "
                "(id, portee_academique, statut) VALUES (1, 'universitaire', 'ACTIF')"
            )
            connection.exec_driver_sql(
                "INSERT INTO demandecreationcercle "
                "(id, utilisateur_id, portee_academique, nom, raison, statut) "
                "VALUES (1, 1, 'universitaire', 'Demande test', 'Test de migration', 'EN_ATTENTE')"
            )

            migration = _charger_migration()
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()

            inspector = sa.inspect(connection)
            demande_columns = {
                column["name"]
                for column in inspector.get_columns("demandecreationcercle")
            }
            assert "matiere_scolaire_id" in demande_columns
            assert any(
                foreign_key.get("name") == "fk_demandecercle_matiere_scolaire"
                for foreign_key in inspector.get_foreign_keys("demandecreationcercle")
            )
            constraints = {
                constraint.get("name")
                for constraint in inspector.get_check_constraints("demandecreationcercle")
            }
            assert "ck_demandecreationcercle_portee_cible_separee" in constraints
            cercle_constraints = {
                constraint.get("name")
                for constraint in inspector.get_check_constraints("cercleetude")
            }
            assert "ck_cercle_portee_cible_separee" in cercle_constraints

            indexes = {
                index.get("name")
                for index in inspector.get_indexes("demandecreationcercle")
            }
            assert "ix_demandecreationcercle_matiere_scolaire_id" in indexes
            assert {
                f"ix_demande_creation_scolaire_unique_{masque:03b}"
                for masque in range(8)
            }.issubset(indexes)

            # Le contenu historique doit rester présent après la réparation.
            assert connection.exec_driver_sql(
                "SELECT count(*) FROM demandecreationcercle"
            ).scalar_one() == 1
    finally:
        engine.dispose()
