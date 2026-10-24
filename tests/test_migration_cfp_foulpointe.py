"""Vérifie l'ajout idempotent des établissements et métiers ETFP confirmés par le METFP."""
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
    spec = importlib.util.spec_from_file_location("migration_etfp_sites_confirmes", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sites_et_offres_sont_ajoutes_sans_doublon_et_restent_en_attente():
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE parcourstechniqueprofessionnel (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, code VARCHAR(120) NOT NULL UNIQUE,
                    secteur VARCHAR(120), filiere VARCHAR(180), metier VARCHAR(180),
                    source_officielle VARCHAR(500), statut_validation VARCHAR(20) NOT NULL,
                    est_actif BOOLEAN NOT NULL, date_creation TIMESTAMP, date_maj TIMESTAMP
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE etablissementscolaire (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, nom VARCHAR(180) NOT NULL,
                    code VARCHAR(180) UNIQUE, type_etablissement VARCHAR(30), secteur VARCHAR(20),
                    region VARCHAR(100), district VARCHAR(100), commune VARCHAR(100),
                    source_officielle VARCHAR(500), est_verifie BOOLEAN NOT NULL,
                    est_actif BOOLEAN NOT NULL, date_creation TIMESTAMP, date_maj TIMESTAMP
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE offreetablissementscolaire (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, etablissement_id INTEGER NOT NULL,
                    code_offre VARCHAR(180) NOT NULL, type_offre VARCHAR(20) NOT NULL,
                    niveau_scolaire_id INTEGER, option_scolaire_id INTEGER, matiere_scolaire_id INTEGER,
                    parcours_etfp_id INTEGER, annee_scolaire VARCHAR(9), source_officielle VARCHAR(500),
                    statut_validation VARCHAR(20) NOT NULL, est_active BOOLEAN NOT NULL,
                    date_creation TIMESTAMP, date_maj TIMESTAMP,
                    UNIQUE(etablissement_id, code_offre, annee_scolaire)
                )
                """
            )
            migration = _charger_migration()
            # Laisse les quatre nouveaux métiers absents pour vérifier leur insertion idempotente.
            nouveaux_codes = {
                "RESTAURATEUR-DE-MEUBLES",
                "INDUSTRIEL-IMPRIMERIE-TECHNICIEN-EN-IMPRIMERIE",
                "TECHNOLOGUE-EN-EQUIPEMENTS-AUDIOVISUELS",
                "JARDINIER-PAYSAGISTE",
            }
            for pathway in migration.PARCOURS:
                if pathway["code"] in nouveaux_codes:
                    continue
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
            assert len(institutions) == 11
            by_name = {row["nom"]: row for row in institutions}
            expected_regions = {
                "CFP FOULPOINTE": "ATSINANANA",
                "LTP BERAVINA": "HAUTE MATSIATRA",
                "LTP ANKAZOBE": "ANALAMANGA",
                "CFP MASINDRAY": "ANALAMANGA",
                "CFP AMPASAMPITO": "ANALAMANGA",
                "LTP ALAROBIA": "ANALAMANGA",
                "LTP AMPASAPITO": "ANALAMANGA",
                "LTP ANKAZONDANDY": "ANALAMANGA",
                "LTP FARATSIHO": "VAKINANKARATRA",
                "CFP ANKAZOMIRIOTRA": "VAKINANKARATRA",
                "LTP MANDOTO": "VAKINANKARATRA",
            }
            assert set(by_name) == set(expected_regions)
            for name, region in expected_regions.items():
                assert by_name[name]["region"] == region
                assert by_name[name]["est_verifie"] == 1
                assert by_name[name]["est_actif"] == 1
            assert by_name["CFP FOULPOINTE"]["commune"] == "Foulpointe"
            assert by_name["LTP BERAVINA"]["commune"] is None

            custom = connection.execute(
                sa.text(
                    "SELECT code, statut_validation FROM parcourstechniqueprofessionnel "
                    "WHERE code IN :codes"
                ).bindparams(sa.bindparam("codes", expanding=True)),
                {"codes": sorted(nouveaux_codes)},
            ).mappings().all()
            assert {row["code"] for row in custom} == nouveaux_codes
            assert all(row["statut_validation"] == "verifie" for row in custom)

            offers = connection.execute(
                sa.text(
                    "SELECT e.nom AS etablissement, o.code_offre, o.statut_validation, "
                    "o.annee_scolaire, o.type_offre FROM offreetablissementscolaire o "
                    "JOIN etablissementscolaire e ON e.id=o.etablissement_id "
                    "ORDER BY e.nom, o.code_offre"
                )
            ).mappings().all()
            assert len(offers) == 75
            expected_offer_counts = {
                "CFP FOULPOINTE": 7,
                "LTP BERAVINA": 23,
                "LTP ANKAZOBE": 4,
                "CFP MASINDRAY": 5,
                "CFP AMPASAMPITO": 1,
                "LTP ALAROBIA": 3,
                "LTP AMPASAPITO": 4,
                "LTP ANKAZONDANDY": 11,
                "LTP FARATSIHO": 4,
                "CFP ANKAZOMIRIOTRA": 6,
                "LTP MANDOTO": 7,
            }
            for name, expected in expected_offer_counts.items():
                records = [row for row in offers if row["etablissement"] == name]
                assert len(records) == expected, (name, len(records), expected)
                assert all(row["type_offre"] == "formation" for row in records)
                assert all(row["statut_validation"] == "a_verifier" for row in records)
                assert all(row["annee_scolaire"] is None for row in records)
                assert len({row["code_offre"] for row in records}) == expected
    finally:
        engine.dispose()
