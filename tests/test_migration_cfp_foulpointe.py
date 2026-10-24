"""Régression pour la migration ETFP historique effectivement appliquée en production."""
import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "d2a7c5e9f840_ajout_cfp_foulpointe.py"
)


def _charger_migration():
    spec = importlib.util.spec_from_file_location("migration_etfp_initiale", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_historique_d2_ajoute_foulpointe_et_beravina_sans_doublon():
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE parcourstechniqueprofessionnel (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code VARCHAR(120) NOT NULL UNIQUE,
                    secteur VARCHAR(120), filiere VARCHAR(180), metier VARCHAR(180),
                    source_officielle VARCHAR(500), statut_validation VARCHAR(20) NOT NULL,
                    est_actif BOOLEAN NOT NULL, date_creation TIMESTAMP, date_maj TIMESTAMP
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE etablissementscolaire (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nom VARCHAR(180) NOT NULL, code VARCHAR(180) UNIQUE,
                    type_etablissement VARCHAR(30), secteur VARCHAR(20),
                    region VARCHAR(100), district VARCHAR(100), commune VARCHAR(100),
                    source_officielle VARCHAR(500), est_verifie BOOLEAN NOT NULL,
                    est_actif BOOLEAN NOT NULL, date_creation TIMESTAMP, date_maj TIMESTAMP
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE offreetablissementscolaire (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    etablissement_id INTEGER NOT NULL, code_offre VARCHAR(180) NOT NULL,
                    type_offre VARCHAR(20) NOT NULL, niveau_scolaire_id INTEGER,
                    option_scolaire_id INTEGER, matiere_scolaire_id INTEGER,
                    parcours_etfp_id INTEGER, annee_scolaire VARCHAR(9),
                    source_officielle VARCHAR(500), statut_validation VARCHAR(20) NOT NULL,
                    est_active BOOLEAN NOT NULL, date_creation TIMESTAMP, date_maj TIMESTAMP,
                    UNIQUE(etablissement_id, code_offre, annee_scolaire)
                )
                """
            )
            migration = _charger_migration()
            for pathway in migration.PARCOURS[:-1]:
                connection.execute(
                    sa.text(
                        "INSERT INTO parcourstechniqueprofessionnel "
                        "(code, secteur, filiere, metier, source_officielle, statut_validation, est_actif) "
                        "VALUES (:code, :secteur, :filiere, :metier, :source, 'verifie', TRUE)"
                    ),
                    {**pathway, "source": migration.SOURCE_CARTOGRAPHIE},
                )

            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.upgrade()

            institutions = connection.execute(
                sa.text(
                    "SELECT nom, region, commune, type_etablissement, est_verifie, est_actif "
                    "FROM etablissementscolaire ORDER BY nom"
                )
            ).mappings().all()
            assert len(institutions) == 2
            by_name = {row["nom"]: row for row in institutions}
            assert by_name["CFP FOULPOINTE"]["region"] == "ATSINANANA"
            assert by_name["CFP FOULPOINTE"]["commune"] == "Foulpointe"
            assert by_name["CFP FOULPOINTE"]["type_etablissement"] == "centre_formation"
            assert by_name["LTP BERAVINA"]["region"] == "HAUTE MATSIATRA"
            assert by_name["LTP BERAVINA"]["type_etablissement"] == "lycee_technique"
            assert all(row["est_verifie"] == 1 and row["est_actif"] == 1 for row in institutions)

            pathways = connection.execute(
                sa.text("SELECT code, statut_validation FROM parcourstechniqueprofessionnel")
            ).mappings().all()
            assert len(pathways) == len(migration.PARCOURS)
            assert any(
                row["code"] == "RESTAURATEUR-DE-MEUBLES" and row["statut_validation"] == "verifie"
                for row in pathways
            )

            offers = connection.execute(
                sa.text(
                    "SELECT e.nom AS etablissement, o.code_offre, o.statut_validation, "
                    "o.annee_scolaire, o.type_offre FROM offreetablissementscolaire o "
                    "JOIN etablissementscolaire e ON e.id=o.etablissement_id"
                )
            ).mappings().all()
            assert len(offers) == 30
            expected = {"CFP FOULPOINTE": 7, "LTP BERAVINA": 23}
            for name, expected_count in expected.items():
                rows = [row for row in offers if row["etablissement"] == name]
                assert len(rows) == expected_count
                assert all(row["type_offre"] == "formation" for row in rows)
                assert all(row["statut_validation"] == "a_verifier" for row in rows)
                assert all(row["annee_scolaire"] is None for row in rows)
                assert len({row["code_offre"] for row in rows}) == expected_count
    finally:
        engine.dispose()
