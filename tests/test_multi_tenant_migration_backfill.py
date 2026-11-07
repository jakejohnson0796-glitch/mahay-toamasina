"""Vérifie la reprise des données d'un schéma antérieur au multi-établissement.

Le fixture reproduit les colonnes historiques pertinentes avant d'appliquer
la migration de tenant : anciennes affiliations utilisateur.institution_id,
cours sans institution_id et notifications sans cours_id.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _charger_migration():
    chemin = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "h1c7e9a2b4d6_multi_tenant_institution.py"
    )
    specification = importlib.util.spec_from_file_location(
        "migration_multi_tenant_fixture", chemin
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_migration_reprend_les_affiliations_et_cours_historiques():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        with engine.begin() as connection:
            # Schéma historique : les tables existent, mais les ajouts de la
            # migration tenant ne sont pas encore présents.
            connection.execute(text("""
                CREATE TABLE etablissementpartenaire (
                    id INTEGER PRIMARY KEY,
                    nom VARCHAR(200) NOT NULL,
                    code VARCHAR(32) NOT NULL UNIQUE,
                    est_actif BOOLEAN NOT NULL DEFAULT 1
                )
            """))
            connection.execute(text("""
                CREATE TABLE utilisateur (
                    id INTEGER PRIMARY KEY,
                    institution_id INTEGER NULL,
                    role VARCHAR(24) NOT NULL,
                    FOREIGN KEY(institution_id)
                        REFERENCES etablissementpartenaire(id)
                )
            """))
            connection.execute(text("""
                CREATE TABLE cours (
                    id INTEGER PRIMARY KEY,
                    nom VARCHAR(200) NOT NULL,
                    matiere VARCHAR(200) NOT NULL,
                    niveau VARCHAR(80) NOT NULL,
                    professeur_id INTEGER NOT NULL,
                    code_invitation VARCHAR(12) NULL UNIQUE,
                    FOREIGN KEY(professeur_id) REFERENCES utilisateur(id)
                )
            """))
            connection.execute(text("""
                CREATE TABLE notification (
                    id INTEGER PRIMARY KEY,
                    utilisateur_id INTEGER NULL
                )
            """))

            connection.execute(text("""
                INSERT INTO etablissementpartenaire (id, nom, code, est_actif)
                VALUES
                    (1, 'Université historique active', 'UNIV-A', 1),
                    (2, 'Institut historique inactif', 'INST-I', 0)
            """))
            connection.execute(text("""
                INSERT INTO utilisateur (id, institution_id, role)
                VALUES
                    (10, 1, 'professeur'),
                    (11, 1, 'admin'),
                    (12, 1, 'etudiant'),
                    (13, 2, 'professeur'),
                    (14, NULL, 'professeur')
            """))
            connection.execute(text("""
                INSERT INTO cours
                    (id, nom, matiere, niveau, professeur_id, code_invitation)
                VALUES
                    (100, 'Cours professeur actif', 'Maths', 'L1', 10, 'ACTIF100'),
                    (101, 'Cours établissement inactif', 'Droit', 'L2', 13, 'INACTIF1'),
                    (102, 'Cours professeur indépendant', 'Histoire', 'L1', 14, 'LIBRE102')
            """))
            connection.execute(text("""
                INSERT INTO notification (id, utilisateur_id)
                VALUES (200, 12)
            """))

            contexte = MigrationContext.configure(connection)
            with Operations.context(contexte):
                _charger_migration().upgrade()

            # L'import historique conserve les rôles attendus et la clé du
            # compte ; le rôle global ne remplace pas le rôle institutionnel.
            membres = connection.execute(text("""
                SELECT institution_id, utilisateur_id, role, est_actif
                FROM membre_etablissement
                ORDER BY utilisateur_id
            """)).all()
            assert [(row[0], row[1], row[2], row[3]) for row in membres] == [
                (1, 10, "professeur", 1),
                (1, 11, "responsable", 1),
                (1, 12, "etudiant", 1),
                (2, 13, "professeur", 1),
            ]

            cours = {
                row.id: row
                for row in connection.execute(text("""
                    SELECT id, institution_id, affectation_institutionnelle_requise,
                           code_invitation
                    FROM cours ORDER BY id
                """)).all()
            }
            assert cours[100].institution_id == 1
            assert cours[100].affectation_institutionnelle_requise in (0, False)
            assert cours[100].code_invitation == "ACTIF100"

            # L'institution désactivée ne doit pas recevoir un cours. Celui-ci
            # est mis en quarantaine plutôt que rendu accessible par défaut.
            assert cours[101].institution_id is None
            assert cours[101].affectation_institutionnelle_requise in (1, True)
            assert cours[101].code_invitation == "INACTIF1"

            # Un professeur indépendant reste dans l'ancien périmètre : ni
            # institution imposée, ni quarantaine.
            assert cours[102].institution_id is None
            assert cours[102].affectation_institutionnelle_requise in (0, False)
            assert cours[102].code_invitation == "LIBRE102"

            notification = connection.execute(text("""
                SELECT id, utilisateur_id, cours_id
                FROM notification WHERE id = 200
            """)).one()
            assert notification.id == 200
            assert notification.utilisateur_id == 12
            assert notification.cours_id is None
    finally:
        engine.dispose()
