from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from scripts.preflight_multi_tenant_migration import (
    activer_lecture_seule,
    construire_rapport,
)


def _creer_schema_historique(connection):
    connection.execute(text("""
        CREATE TABLE etablissementpartenaire (
            id INTEGER PRIMARY KEY,
            nom VARCHAR(120) NOT NULL,
            est_actif BOOLEAN NOT NULL
        )
    """))
    connection.execute(text("""
        CREATE TABLE utilisateur (
            id INTEGER PRIMARY KEY,
            institution_id INTEGER NULL,
            role VARCHAR(24) NOT NULL
        )
    """))
    connection.execute(text("""
        CREATE TABLE cours (
            id INTEGER PRIMARY KEY,
            professeur_id INTEGER NOT NULL
        )
    """))
    connection.execute(text("""
        CREATE TABLE notification (
            id INTEGER PRIMARY KEY,
            utilisateur_id INTEGER NULL
        )
    """))
    connection.execute(text("""
        INSERT INTO etablissementpartenaire (id, nom, est_actif)
        VALUES (1, 'ETABLISSEMENT_FICTIF_A', TRUE),
               (2, 'ETABLISSEMENT_FICTIF_B', FALSE)
    """))
    connection.execute(text("""
        INSERT INTO utilisateur (id, institution_id, role)
        VALUES (10, 1, 'professeur'),
               (11, 2, 'admin'),
               (12, NULL, 'professeur'),
               (13, 1, 'sponsor')
    """))
    connection.execute(text("""
        INSERT INTO cours (id, professeur_id)
        VALUES (100, 10), (101, 11), (102, 12), (103, 13)
    """))
    connection.execute(text("""
        INSERT INTO notification (id, utilisateur_id)
        VALUES (200, 12), (201, 13)
    """))


def test_preflight_ne_retourne_que_des_compteurs_agreges():
    moteur = create_engine("sqlite://")
    try:
        with moteur.begin() as connection:
            _creer_schema_historique(connection)
            rapport = construire_rapport(connection)

        assert rapport["status"] == "ok"
        assert rapport["lecture_seule"] is True
        assert rapport["migration_executee"] is False
        assert rapport["compteurs"]["etablissements"] == {
            "total": 2, "actifs": 1, "inactifs": 1
        }
        assert rapport["compteurs"]["utilisateurs"]["total"] == 4
        assert rapport["compteurs"]["utilisateurs"]["roles_non_reconnus_rattaches"] == 1
        assert rapport["compteurs"]["cours"] == {
            "total": 4,
            "candidats_affectation_automatique": 1,
            "candidats_quarantaine": 1,
            "hors_backfill_automatique": 2,
        }
        assert rapport["compteurs"]["notifications"]["total"] == 2

        sortie = json.dumps(rapport, ensure_ascii=False)
        assert "ETABLISSEMENT_FICTIF" not in sortie
        assert "professeur_id" not in sortie
        assert '"id"' not in sortie
    finally:
        moteur.dispose()


def test_preflight_signale_un_schema_incomplet_sans_lire_de_lignes():
    moteur = create_engine("sqlite://")
    try:
        with moteur.begin() as connection:
            connection.execute(text("CREATE TABLE utilisateur (id INTEGER PRIMARY KEY)"))
            rapport = construire_rapport(connection)
        assert rapport["status"] == "schema_incomplet"
        assert rapport["migration_executee"] is False
        assert "etablissementpartenaire" in rapport["tables_manquantes"]
        assert "notification" in rapport["tables_manquantes"]
    finally:
        moteur.dispose()


def test_preflight_sqlite_est_strictement_en_lecture_seule():
    moteur = create_engine("sqlite://")
    try:
        with moteur.connect() as connection:
            connection.execute(text("CREATE TABLE test_guard (id INTEGER PRIMARY KEY)"))
            connection.commit()
            activer_lecture_seule(connection)
            with pytest.raises(DBAPIError):
                connection.execute(text("INSERT INTO test_guard (id) VALUES (1)"))
    finally:
        moteur.dispose()
