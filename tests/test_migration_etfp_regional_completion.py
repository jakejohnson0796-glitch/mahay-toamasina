"""End-to-end idempotence for the ETFP snapshot and the missing regional entries."""
import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


ROOT = Path(__file__).resolve().parents[1]
BASE_MIGRATION = ROOT / "alembic" / "versions" / "b7d4e9c2a610_offres_etfp_etablissements.py"
D2_MIGRATION = ROOT / "alembic" / "versions" / "d2a7c5e9f840_ajout_cfp_foulpointe.py"
E3_MIGRATION = ROOT / "alembic" / "versions" / "e3b9c6a1d740_completer_etfp_analamanga_vakinankaratra.py"
E4_MIGRATION = ROOT / "alembic" / "versions" / "f2d8c1a4e630_etablissements_etfp_anosy.py"


def _charger(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_snapshot_etfp_regional_est_additif_idempotent_et_ne_publie_pas_les_offres():
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

            base = _charger(BASE_MIGRATION, "migration_catalogue_etfp_base")
            d2 = _charger(D2_MIGRATION, "migration_etfp_d2")
            e3 = _charger(E3_MIGRATION, "migration_etfp_e3")
            e4 = _charger(E4_MIGRATION, "migration_etfp_e4")

            # Représente les taxonomies normalisées introduites dans la base par b7.
            codes_base = set()
            for secteur, filiere, metier in base.PARCOURS.values():
                code = base._slug("-".join(part for part in (secteur, filiere, metier) if part))
                if code in codes_base:
                    continue
                codes_base.add(code)
                connection.execute(
                    sa.text(
                        "INSERT INTO parcourstechniqueprofessionnel "
                        "(code, secteur, filiere, metier, source_officielle, statut_validation, est_actif) "
                        "VALUES (:code, :secteur, :filiere, :metier, :source, 'verifie', TRUE)"
                    ),
                    {
                        "code": code,
                        "secteur": secteur or None,
                        "filiere": filiere or None,
                        "metier": metier,
                        "source": base.SOURCE_CARTOGRAPHIE,
                    },
                )

            with Operations.context(MigrationContext.configure(connection)):
                # La migration D2 doit rester historiquement limitée à CFP Foulpointe
                # et LTP Beravina, conformément à la révision déjà appliquée.
                d2.upgrade()
                # Deux passages de E3 simulent plusieurs redémarrages après le rattrapage.
                e3.upgrade()
                e3.upgrade()
                # La migration Anosy peut elle aussi être relancée sans doublon.
                e4.upgrade()
                e4.upgrade()

            establishments = connection.execute(
                sa.text(
                    "SELECT nom, region, type_etablissement, est_verifie, est_actif "
                    "FROM etablissementscolaire ORDER BY nom"
                )
            ).mappings().all()
            by_name = {row["nom"]: row for row in establishments}
            assert len(by_name) == 18
            assert by_name["CFP FOULPOINTE"]["region"] == "ATSINANANA"
            assert by_name["LTP BERAVINA"]["region"] == "HAUTE MATSIATRA"
            expected_regions = {
                "LTP ANKAZOBE": "ANALAMANGA",
                "LTP SOAVINA": "ANALAMANGA",
                "CFP MASINDRAY": "ANALAMANGA",
                "LTP ALAROBIA AMBATOMANGA": "ANALAMANGA",
                "LTP MANJAKANDRIANA": "ANALAMANGA",
                "LTP MANTASOA": "ANALAMANGA",
                "CFPF ANTSOFINONDRY SABOTSY NAMEHENA": "ANALAMANGA",
                "LT AMPEFILOHA - LTA (EX-CTM)": "ANALAMANGA",
                "LTP AMPEFILOHA": "ANALAMANGA",
                "CFPF TSIMBAZAZA": "ANALAMANGA",
                "LTP FARATSIHO": "VAKINANKARATRA",
                "CFP ANKAZOMIRIOTRA": "VAKINANKARATRA",
                "LTP MANDOTO": "VAKINANKARATRA",
                "LTP BETROKA": "ANOSY",
                "CFPF ISOANALA": "ANOSY",
                "LTA AMPASY NAHAMPOANA": "ANOSY",
            }
            for name, region in expected_regions.items():
                assert by_name[name]["region"] == region
                assert by_name[name]["est_verifie"] == 1
                assert by_name[name]["est_actif"] == 1
            assert len(codes_base) == len(set(codes_base))

            pathways = connection.execute(
                sa.text("SELECT code, statut_validation, source_officielle FROM parcourstechniqueprofessionnel")
            ).mappings().all()
            pathway_codes = {row["code"] for row in pathways}
            assert len(pathway_codes) == len(pathways)
            assert "RESTAURATEUR-DE-MEUBLES" in pathway_codes
            assert "JARDINIER-PAYSAGISTE" in pathway_codes
            assert "BOULANGER-PATISSIER" in pathway_codes
            assert "OUVRIER-DE-FERME-D-ELEVAGE" in pathway_codes
            assert all(row["statut_validation"] == "verifie" for row in pathways)

            offers = connection.execute(
                sa.text(
                    "SELECT e.nom AS etablissement, o.code_offre, o.statut_validation, "
                    "o.annee_scolaire, o.type_offre FROM offreetablissementscolaire o "
                    "JOIN etablissementscolaire e ON e.id=o.etablissement_id"
                )
            ).mappings().all()
            assert len(offers) == 117
            expected_offers = {
                "CFP FOULPOINTE": 9,
                "LTP BERAVINA": 23,
                "LTP ANKAZOBE": 4,
                "LTP SOAVINA": 3,
                "CFP MASINDRAY": 5,
                "LTP ALAROBIA AMBATOMANGA": 3,
                "LTP MANJAKANDRIANA": 8,
                "LTP MANTASOA": 2,
                "CFPF ANTSOFINONDRY SABOTSY NAMEHENA": 4,
                "LT AMPEFILOHA - LTA (EX-CTM)": 3,
                "LTP AMPEFILOHA": 1,
                "CFPF TSIMBAZAZA": 5,
                "LTP FARATSIHO": 4,
                "CFP ANKAZOMIRIOTRA": 6,
                "LTP MANDOTO": 7,
                "LTP BETROKA": 16,
                "CFPF ISOANALA": 9,
                "LTA AMPASY NAHAMPOANA": 5,
            }
            for name, expected in expected_offers.items():
                records = [row for row in offers if row["etablissement"] == name]
                assert len(records) == expected, (name, len(records), expected)
                assert all(row["type_offre"] == "formation" for row in records)
                assert all(row["statut_validation"] == "a_verifier" for row in records)
                assert all(row["annee_scolaire"] is None for row in records)
                assert len({row["code_offre"] for row in records}) == expected
            assert len({(row["etablissement"], row["code_offre"]) for row in offers}) == 117
    finally:
        engine.dispose()
