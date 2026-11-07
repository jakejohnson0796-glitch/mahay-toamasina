"""Préflight non destructif de la migration multiétablissements.

Le script n'affiche que des compteurs et des indicateurs techniques agrégés.
Il n'exécute aucune migration et n'extrait aucune ligne métier.
DATABASE_URL est lu depuis l'environnement et n'est jamais affiché.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection


TABLES_REQUISES = {
    "etablissementpartenaire": {"id", "est_actif"},
    "utilisateur": {"id", "institution_id", "role"},
    "cours": {"id", "professeur_id"},
    "notification": {"id"},
}


def activer_lecture_seule(connection: Connection) -> None:
    """Force une transaction read-only avant toute requête de contrôle."""
    dialecte = connection.dialect.name
    if dialecte == "postgresql":
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
    elif dialecte == "sqlite":
        connection.exec_driver_sql("PRAGMA query_only = ON")
    else:
        raise RuntimeError("Le préflight ne prend en charge que PostgreSQL et SQLite.")


def _entier(row: Any, cle: str) -> int:
    valeur = row._mapping[cle]
    return int(valeur or 0)


def construire_rapport(connection: Connection) -> dict[str, Any]:
    """Produit exclusivement des compteurs, sans valeurs issues des lignes."""
    inspecteur = inspect(connection)
    tables = set(inspecteur.get_table_names())
    colonnes = {
        table: {colonne["name"] for colonne in inspecteur.get_columns(table)}
        for table in TABLES_REQUISES
        if table in tables
    }
    tables_manquantes = sorted(set(TABLES_REQUISES) - tables)
    colonnes_manquantes = {
        table: sorted(attendues - colonnes.get(table, set()))
        for table, attendues in TABLES_REQUISES.items()
        if table in tables and attendues - colonnes.get(table, set())
    }
    if tables_manquantes or colonnes_manquantes:
        return {
            "status": "schema_incomplet",
            "lecture_seule": True,
            "migration_executee": False,
            "tables_manquantes": tables_manquantes,
            "colonnes_manquantes": colonnes_manquantes,
            "message": "Préflight interrompu ; aucune donnée modifiée.",
        }

    etablissements = connection.execute(text("""
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN est_actif IS TRUE THEN 1 ELSE 0 END), 0) AS actifs,
               COALESCE(SUM(CASE WHEN est_actif IS NOT TRUE THEN 1 ELSE 0 END), 0) AS inactifs
        FROM etablissementpartenaire
    """)).one()
    utilisateurs = connection.execute(text("""
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN institution_id IS NOT NULL THEN 1 ELSE 0 END), 0) AS rattaches,
               COALESCE(SUM(CASE WHEN institution_id IS NOT NULL
                   AND lower(CAST(role AS VARCHAR)) = 'etudiant' THEN 1 ELSE 0 END), 0) AS etudiants,
               COALESCE(SUM(CASE WHEN institution_id IS NOT NULL
                   AND lower(CAST(role AS VARCHAR)) = 'professeur' THEN 1 ELSE 0 END), 0) AS professeurs,
               COALESCE(SUM(CASE WHEN institution_id IS NOT NULL
                   AND lower(CAST(role AS VARCHAR)) = 'admin' THEN 1 ELSE 0 END), 0) AS admins,
               COALESCE(SUM(CASE WHEN institution_id IS NOT NULL
                   AND lower(CAST(role AS VARCHAR)) NOT IN ('etudiant', 'professeur', 'admin')
                   THEN 1 ELSE 0 END), 0) AS roles_non_reconnus_rattaches
        FROM utilisateur
    """)).one()
    cours = connection.execute(text("""
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN u.institution_id IS NOT NULL
                   AND ep.est_actif IS TRUE
                   AND lower(CAST(u.role AS VARCHAR)) IN ('professeur', 'admin')
                   THEN 1 ELSE 0 END), 0) AS candidats_affectation_automatique,
               COALESCE(SUM(CASE WHEN u.institution_id IS NOT NULL
                   AND (ep.id IS NULL OR ep.est_actif IS NOT TRUE)
                   AND lower(CAST(u.role AS VARCHAR)) IN ('professeur', 'admin')
                   THEN 1 ELSE 0 END), 0) AS candidats_quarantaine,
               COALESCE(SUM(CASE WHEN u.id IS NULL OR u.institution_id IS NULL
                   OR lower(CAST(u.role AS VARCHAR)) NOT IN ('professeur', 'admin')
                   THEN 1 ELSE 0 END), 0) AS cours_hors_backfill_automatique
        FROM cours AS c
        LEFT JOIN utilisateur AS u ON u.id = c.professeur_id
        LEFT JOIN etablissementpartenaire AS ep ON ep.id = u.institution_id
    """)).one()
    notifications = connection.execute(
        text("SELECT COUNT(*) AS total FROM notification")
    ).one()

    rapport: dict[str, Any] = {
        "status": "ok",
        "dialecte": connection.dialect.name,
        "lecture_seule": True,
        "migration_executee": False,
        "schema": {
            "membre_etablissement_present": "membre_etablissement" in tables,
            "cours_institution_id_present": "institution_id" in colonnes["cours"],
            "cours_quarantaine_present": "affectation_institutionnelle_requise" in colonnes["cours"],
            "notification_cours_id_present": "cours_id" in colonnes["notification"],
        },
        "compteurs": {
            "etablissements": {
                "total": _entier(etablissements, "total"),
                "actifs": _entier(etablissements, "actifs"),
                "inactifs": _entier(etablissements, "inactifs"),
            },
            "utilisateurs": {
                "total": _entier(utilisateurs, "total"),
                "rattaches": _entier(utilisateurs, "rattaches"),
                "etudiants_rattaches": _entier(utilisateurs, "etudiants"),
                "professeurs_rattaches": _entier(utilisateurs, "professeurs"),
                "admins_rattaches": _entier(utilisateurs, "admins"),
                "roles_non_reconnus_rattaches": _entier(utilisateurs, "roles_non_reconnus_rattaches"),
            },
            "cours": {
                "total": _entier(cours, "total"),
                "candidats_affectation_automatique": _entier(cours, "candidats_affectation_automatique"),
                "candidats_quarantaine": _entier(cours, "candidats_quarantaine"),
                "hors_backfill_automatique": _entier(cours, "cours_hors_backfill_automatique"),
            },
            "notifications": {"total": _entier(notifications, "total")},
        },
        "rls": None,
        "alertes": [],
        "message": "Préflight en lecture seule uniquement ; aucune migration ni écriture effectuée.",
    }

    if "membre_etablissement" in tables:
        colonnes_membres = {
            colonne["name"] for colonne in inspecteur.get_columns("membre_etablissement")
        }
        attendues = {"institution_id", "utilisateur_id", "role", "est_actif"}
        if attendues.issubset(colonnes_membres):
            membres = connection.execute(text("""
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN est_actif IS TRUE THEN 1 ELSE 0 END), 0) AS actifs,
                       COALESCE(SUM(CASE WHEN est_actif IS TRUE AND role = 'responsable'
                           THEN 1 ELSE 0 END), 0) AS responsables_actifs
                FROM membre_etablissement
            """)).one()
            affiliations_multiples = connection.execute(text("""
                SELECT COUNT(*) AS total
                FROM (
                    SELECT utilisateur_id
                    FROM membre_etablissement
                    WHERE est_actif IS TRUE
                    GROUP BY utilisateur_id
                    HAVING COUNT(DISTINCT institution_id) > 1
                ) AS affiliations
            """)).one()
            rapport["compteurs"]["membres_etablissement"] = {
                "total": _entier(membres, "total"),
                "actifs": _entier(membres, "actifs"),
                "responsables_actifs": _entier(membres, "responsables_actifs"),
                "utilisateurs_multi_affilies_actifs": _entier(affiliations_multiples, "total"),
            }

        if connection.dialect.name == "postgresql":
            rls = connection.execute(text("""
                SELECT c.relrowsecurity AS active,
                       c.relforcerowsecurity AS forcee,
                       (SELECT COUNT(*) FROM pg_policies p
                        WHERE p.schemaname = n.nspname AND p.tablename = c.relname) AS politiques,
                       COALESCE((SELECT r.rolsuper OR r.rolbypassrls
                                 FROM pg_roles r WHERE r.rolname = current_user), FALSE) AS role_contourne_rls
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema()
                  AND c.relname = 'membre_etablissement'
            """)).first()
            if rls:
                rapport["rls"] = {
                    "active": bool(rls.active),
                    "forcee": bool(rls.forcee),
                    "nombre_politiques": int(rls.politiques or 0),
                    "connexion_ci_bypassrls": bool(rls.role_contourne_rls),
                }
                if not rls.active:
                    rapport["alertes"].append("RLS est désactivé sur membre_etablissement.")
                elif rls.politiques == 0 and not rls.role_contourne_rls:
                    rapport["alertes"].append(
                        "RLS est actif sans politique et le rôle de connexion ne contourne pas RLS ; vérifier le rôle utilisé par l'application."
                    )

    if _entier(utilisateurs, "roles_non_reconnus_rattaches"):
        rapport["alertes"].append(
            "Des comptes synthétiques rattachés utilisent des rôles non repris automatiquement ; examiner uniquement le compteur agrégé."
        )
    if rapport["schema"]["membre_etablissement_present"] and not (
        rapport["schema"]["cours_institution_id_present"]
        and rapport["schema"]["cours_quarantaine_present"]
        and rapport["schema"]["notification_cours_id_present"]
    ):
        rapport["alertes"].append("Schéma multiétablissements partiel : vérifier la révision Alembic.")
    return rapport


def executer_preflight(database_url: str) -> dict[str, Any]:
    moteur = create_engine(database_url, pool_pre_ping=True)
    try:
        with moteur.connect() as connection:
            activer_lecture_seule(connection)
            return construire_rapport(connection)
    finally:
        moteur.dispose()


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print(
            json.dumps({
                "status": "configuration_absente",
                "message": "Définir DATABASE_URL dans l'environnement privé ; ne pas l'afficher ni la committer.",
            }, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2
    try:
        rapport = executer_preflight(database_url)
    except Exception as erreur:  # Ne jamais imprimer d'exception pouvant contenir l'URL.
        print(
            json.dumps({
                "status": "erreur",
                "type_erreur": type(erreur).__name__,
                "message": "Préflight interrompu. Aucune migration n'a été exécutée ; vérifier la configuration hors des journaux partagés.",
            }, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(rapport, ensure_ascii=False, indent=2))
    return 0 if rapport["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
