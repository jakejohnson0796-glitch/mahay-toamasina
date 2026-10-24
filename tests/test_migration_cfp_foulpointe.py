"""Vérifie l'ajout idempotent du CFP Foulpointe et le statut prudent de ses offres."""
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
    spec = importlib.util.spec_from_file_location("migration_cfp_foulpointe", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cfp_foulpointe_et_offres_sont_ajoutes_sans_doublon_et_restent_en_attente():
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE parcourstechniqueprofessionnel (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code VARCHAR(120) NOT NULL UNIQUE,
                    secteur VARCHAR(120),
                    filiere VARCHAR(180),
                    metier VARCHAR(180),
                    source_officielle VARCHAR(500),
                    statut_validation VARCHAR(20) NOT NULL,
                    est_actif BOOLEAN NOT NULL,
                    date_creation TIMESTAMP,
                    date_maj TIMESTAMP
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE etablissementscolaire (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nom VARCHAR(180) NOT NULL,
                    code VARCHAR(180) UNIQUE,
                    type_etablissement VARCHAR(30),
                    secteur VARCHAR(20),
                    region VARCHAR(100),
                    district VARCHAR(100),
                    commune VARCHAR(100),
                    source_officielle VARCHAR(500),
                    est_verifie BOOLEAN NOT NULL,
                    est_actif BOOLEAN NOT NULL,
                    date_creation TIMESTAMP,
                    date_maj TIMESTAMP
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE offreetablissementscolaire (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    etablissement_id INTEGER NOT NULL,
                    code_offre VARCHAR(180) NOT NULL,
                    type_offre VARCHAR(20) NOT NULL,
                    niveau_scolaire_id INTEGER,
                    option_scolaire_id INTEGER,
                    matiere_scolaire_id INTEGER,
                    parcours_etfp_id INTEGER,
                    annee_scolaire VARCHAR(9),
                    source_officielle VARCHAR(500),
                    statut_validation VARCHAR(20) NOT NULL,
                    est_active BOOLEAN NOT NULL,
                    date_creation TIMESTAMP,
                    date_maj TIMESTAMP,
                    UNIQUE(etablissement_id, code_offre)
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

            # Simule deux démarrages successifs sur une base existante.
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.upgrade()

            establishment_rows = connection.execute(
                sa.text(
                    "SELECT nom, region, commune, type_etablissement, est_verifie, est_actif "
                    "FROM etablissementscolaire"
                )
            ).mappings().all()
            assert len(establishment_rows) == 1
            assert establishment_rows[0]["nom"] == "CFP FOULPOINTE"
            assert establishment_rows[0]["region"] == "ATSINANANA"
            assert establishment_rows[0]["commune"] == "Foulpointe"
            assert establishment_rows[0]["type_etablissement"] == "centre_formation"
            assert establishment_rows[0]["est_verifie"] == 1
            assert establishment_rows[0]["est_actif"] == 1

            pathway_rows = connection.execute(
                sa.text(
                    "SELECT code, statut_validation FROM parcourstechniqueprofessionnel "
                    "WHERE code='RESTAURATEUR-DE-MEUBLES'"
                )
            ).mappings().all()
            assert len(pathway_rows) == 1
            assert pathway_rows[0]["statut_validation"] == "verifie"

            offer_rows = connection.execute(
                sa.text(
                    "SELECT code_offre, statut_validation, annee_scolaire, type_offre "
                    "FROM offreetablissementscolaire ORDER BY code_offre"
                )
            ).mappings().all()
            assert len(offer_rows) == 7
            assert all(row["type_offre"] == "formation" for row in offer_rows)
            assert all(row["statut_validation"] == "a_verifier" for row in offer_rows)
            assert all(row["annee_scolaire"] is None for row in offer_rows)
            assert len({row["code_offre"] for row in offer_rows}) == 7
    finally:
        engine.dispose()
