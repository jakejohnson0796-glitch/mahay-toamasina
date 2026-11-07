"""Valide le backfill multiétablissement sur PostgreSQL avec des données synthétiques.

Ce test ne se connecte jamais à la base de production et ne lit aucune donnée réelle.
Il crée un schéma temporaire isolé, y reproduit les seules colonnes historiques
utilisées par la migration, applique celle-ci deux fois, puis supprime le schéma.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from scripts.preflight_multi_tenant_migration import cible_ci_autorisee


def _charger_migration():
    chemin = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "h1c7e9a2b4d6_multi_tenant_institution.py"
    )
    specification = importlib.util.spec_from_file_location(
        "migration_multi_tenant_postgres_fixture", chemin
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _database_url_postgres_ci_autorisee() -> str:
    """Retourne uniquement l'URL du PostgreSQL local éphémère de GitHub Actions."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL absent : test PostgreSQL réservé au job postgres-smoke.")
    if sa.engine.make_url(url).get_backend_name() != "postgresql":
        pytest.skip("Ce test nécessite PostgreSQL ; aucun schéma n'est créé sur SQLite.")
    if not cible_ci_autorisee(url):
        raise ValueError(
            "Cible PostgreSQL refusée : ce test destructif de schéma est limité "
            "au PostgreSQL local éphémère de GitHub Actions. Aucune connexion "
            "n'a été ouverte."
        )
    return url


@pytest.mark.parametrize(
    ("url", "github_actions"),
    [
        ("postgresql://postgres:test@db.example.invalid:5432/production", "true"),
        ("postgresql://postgres:test@localhost:5432/mahay_ci", "false"),
    ],
)
def test_migration_postgres_refuse_les_cibles_non_jetables(
    monkeypatch, url: str, github_actions: str
):
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("GITHUB_ACTIONS", github_actions)

    with pytest.raises(ValueError, match="Cible PostgreSQL refusée"):
        _database_url_postgres_ci_autorisee()


def test_backfill_postgres_historique_est_conserve_et_idempotent():
    url = _database_url_postgres_ci_autorisee()

    engine = sa.create_engine(url, pool_pre_ping=True)
    schema = "test_migration_tenant_" + uuid4().hex
    migration = _charger_migration()

    try:
        with engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.commit()
            try:
                connection.exec_driver_sql(f'SET search_path TO "{schema}"')
                connection.commit()

                with connection.begin():
                    connection.execute(text("""
                        CREATE TABLE etablissementpartenaire (
                            id INTEGER PRIMARY KEY,
                            nom VARCHAR(200) NOT NULL,
                            code VARCHAR(32) NOT NULL UNIQUE,
                            est_actif BOOLEAN NOT NULL DEFAULT TRUE
                        )
                    """))
                    connection.execute(text("""
                        CREATE TABLE utilisateur (
                            id INTEGER PRIMARY KEY,
                            institution_id INTEGER NULL
                                REFERENCES etablissementpartenaire(id),
                            role VARCHAR(24) NOT NULL
                        )
                    """))
                    connection.execute(text("""
                        CREATE TABLE cours (
                            id INTEGER PRIMARY KEY,
                            nom VARCHAR(200) NOT NULL,
                            matiere VARCHAR(200) NOT NULL,
                            niveau VARCHAR(80) NOT NULL,
                            professeur_id INTEGER NOT NULL REFERENCES utilisateur(id),
                            code_invitation VARCHAR(12) NULL UNIQUE
                        )
                    """))
                    connection.execute(text("""
                        CREATE TABLE notification (
                            id INTEGER PRIMARY KEY,
                            utilisateur_id INTEGER NULL REFERENCES utilisateur(id)
                        )
                    """))
                    connection.execute(text("""
                        INSERT INTO etablissementpartenaire (id, nom, code, est_actif)
                        VALUES
                            (1, 'Université synthétique active', 'SYN-A', TRUE),
                            (2, 'Institut synthétique inactif', 'SYN-I', FALSE)
                    """))
                    connection.execute(text("""
                        INSERT INTO utilisateur (id, institution_id, role)
                        VALUES
                            (10, 1, 'professeur'),
                            (11, 1, 'admin'),
                            (12, 1, 'etudiant'),
                            (13, 2, 'professeur'),
                            (14, NULL, 'professeur'),
                            (15, 1, 'sponsor')
                    """))
                    connection.execute(text("""
                        INSERT INTO cours
                            (id, nom, matiere, niveau, professeur_id, code_invitation)
                        VALUES
                            (100, 'Cours synthétique actif', 'Maths', 'L1', 10, 'SYN100'),
                            (101, 'Cours synthétique inactif', 'Droit', 'L2', 13, 'SYN101'),
                            (102, 'Cours synthétique indépendant', 'Histoire', 'L1', 14, 'SYN102')
                    """))
                    connection.execute(text("""
                        INSERT INTO notification (id, utilisateur_id)
                        VALUES (200, 12)
                    """))

                    contexte = MigrationContext.configure(connection)
                    with Operations.context(contexte):
                        migration.upgrade()

                    membres = connection.execute(text("""
                        SELECT institution_id, utilisateur_id, role, est_actif
                        FROM membre_etablissement
                        ORDER BY utilisateur_id
                    """)).all()
                    assert [(r[0], r[1], r[2], r[3]) for r in membres] == [
                        (1, 10, "professeur", True),
                        (1, 11, "responsable", True),
                        (1, 12, "etudiant", True),
                        (2, 13, "professeur", True),
                    ]
                    # Un rôle global sponsor n'est pas assimilé implicitement
                    # à un étudiant institutionnel.
                    assert connection.execute(text("""
                        SELECT COUNT(*) FROM membre_etablissement
                        WHERE utilisateur_id = 15
                    """)).scalar_one() == 0

                    cours = {
                        r.id: r
                        for r in connection.execute(text("""
                            SELECT id, institution_id,
                                   affectation_institutionnelle_requise,
                                   code_invitation
                            FROM cours ORDER BY id
                        """)).all()
                    }
                    assert cours[100].institution_id == 1
                    assert cours[100].affectation_institutionnelle_requise is False
                    assert cours[101].institution_id is None
                    assert cours[101].affectation_institutionnelle_requise is True
                    assert cours[102].institution_id is None
                    assert cours[102].affectation_institutionnelle_requise is False
                    assert [cours[i].code_invitation for i in (100, 101, 102)] == [
                        "SYN100", "SYN101", "SYN102"
                    ]

                    notification = connection.execute(text("""
                        SELECT id, utilisateur_id, cours_id
                        FROM notification WHERE id = 200
                    """)).one()
                    assert (notification.id, notification.utilisateur_id) == (200, 12)
                    assert notification.cours_id is None

                    rls = connection.execute(text("""
                        SELECT c.relrowsecurity
                        FROM pg_class AS c
                        JOIN pg_namespace AS n ON n.oid = c.relnamespace
                        WHERE n.nspname = :schema
                          AND c.relname = 'membre_etablissement'
                    """), {"schema": schema}).scalar_one()
                    assert rls is True

                    # Simule une situation réelle ambiguë : un professeur
                    # possède désormais une seconde appartenance active et un
                    # nouveau cours sans tenant. La migration ne doit pas
                    # choisir arbitrairement l'un des deux établissements.
                    connection.execute(text("""
                        INSERT INTO etablissementpartenaire (id, nom, code, est_actif)
                        VALUES (3, 'Deuxième établissement synthétique', 'SYN-B', TRUE)
                    """))
                    connection.execute(text("""
                        INSERT INTO membre_etablissement
                            (institution_id, utilisateur_id, role, est_actif)
                        VALUES (3, 10, 'professeur', TRUE)
                    """))
                    connection.execute(text("""
                        INSERT INTO cours
                            (id, nom, matiere, niveau, professeur_id, code_invitation)
                        VALUES (103, 'Cours multi-affilié', 'Physique', 'L2', 10, 'SYN103')
                    """))

                    # Le second passage doit conserver les appartenances,
                    # détecter l'ambiguïté et mettre le cours en quarantaine.
                    with Operations.context(contexte):
                        migration.upgrade()

                    assert connection.execute(
                        text("SELECT COUNT(*) FROM membre_etablissement")
                    ).scalar_one() == 5
                    cours_ambigu = connection.execute(text("""
                        SELECT institution_id, affectation_institutionnelle_requise
                        FROM cours WHERE id = 103
                    """)).one()
                    assert cours_ambigu.institution_id is None
                    assert cours_ambigu.affectation_institutionnelle_requise is True
                    assert connection.execute(
                        text("SELECT COUNT(*) FROM cours")
                    ).scalar_one() == 4
                    assert connection.execute(
                        text("SELECT COUNT(*) FROM notification")
                    ).scalar_one() == 1
            finally:
                connection.rollback()
                connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                connection.commit()
    finally:
        engine.dispose()
