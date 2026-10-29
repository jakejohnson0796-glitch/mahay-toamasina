"""
Smoke test PostgreSQL du référentiel académique Toamasina.

Ce test vérifie le chemin de production (PostgreSQL + Alembic + startup
FastAPI + import de la source issue du classeur fourni) sur une base neuve,
puis vérifie l'idempotence et une recherche HTTP réelle dans /cercles.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import re
import secrets
from types import SimpleNamespace
import time
import unicodedata

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import or_
from sqlmodel import Session, select, func

from app.main import app
from app.models import (
    CercleEtude,
    Domaine,
    Document,
    Faculte,
    FicheRevisionDocument,
    Filiere,
    Mention,
    MatiereScolaire,
    NiveauScolaire,
    Notification,
    OptionScolaire,
    ProgrammeMatiereScolaire,
    ProgressionNotion,
    ReferentielScolaire,
    ProgrammeUniversitaire,
    RoleUtilisateur,
    StatutDocument,
    StatutFicheRevisionDocument,
    StatutTacheIA,
    TacheIA,
    TypeDocument,
    TypeNotification,
    Universite,
    Utilisateur,
)
from app import ai_queue, ai_worker, course_revision
from app.routers import documents_router
from scripts.import_academic_data import importer


SOURCE = Path(__file__).resolve().parent.parent / "mahay_toamasina_referentiel_source.json"
SOURCE_SHA256 = "fefcd0e5b0886ec181f74d568378afca87c7f1fd54e0b1a30790b249d89ca2ed"

FACULTES_SOURCE_VERS_BASE = {
    "faculte deg": "droit, economie, gestion, mathematiques et informatique (degmia)",
    "faculte des sciences et technologie": "sciences et technologies",
    "ecole normale superieure": "ecole normale superieure (ens)",
    "faculte des lettres et sciences humaines": "lettres et sciences humaines",
}


def _normaliser(texte: str | None) -> str:
    if not texte:
        return ""
    texte = texte.strip().replace("\u2019", "'")
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texte).lower()


def _source() -> dict:
    assert SOURCE.exists(), f"Source du référentiel absente du dépôt : {SOURCE}"
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    assert payload["sha256"] == SOURCE_SHA256
    assert _normaliser(payload["universite"]) == "universite de toamasina"
    assert payload["hierarchie"] == ["Université", "Composante", "Domaine", "Mention", "Niveau", "Parcours"]
    assert len(payload["formations"]) == 157
    assert {ligne["domaine"] for ligne in payload["formations"]} == {
        "Droit et sciences politiques",
        "Sciences économiques",
        "Sciences de gestion",
        "Sciences et technologie",
        "Sciences de l’éducation",
        "Arts, Lettres et Sciences Humaines",
    }
    assert len({ligne["mention"] for ligne in payload["formations"]}) == 24
    return payload


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith(("postgresql://", "postgresql+psycopg2://")),
    reason="Smoke test réservé à PostgreSQL",
)
def test_postgres_demarrage_import_referentiel_idempotence_et_recherche():
    payload = _source()

    # Le démarrage lance maintenant la maintenance lourde du référentiel
    # en arrière-plan. Le smoke test attend donc explicitement la readiness
    # métier avant de vérifier les données.
    with TestClient(app) as client:
        pret = False
        for _ in range(100):
            readiness = client.get("/ready")
            if readiness.status_code == 200:
                pret = True
                break
            time.sleep(0.1)
        assert pret, readiness.text

        response = client.get("/")
        assert response.status_code == 200
        cercles_page = client.get("/cercles")
        assert cercles_page.status_code == 200

    from app.database import engine

    with Session(engine) as session:
        universites = {u.nom for u in session.exec(select(Universite)).all()}
        domaines = {d.nom for d in session.exec(select(Domaine)).all()}
        mentions = session.exec(select(Mention)).all()

        assert any(_normaliser(nom) == "universite de toamasina" for nom in universites)

        domaines_source = {ligne["domaine"] for ligne in payload["formations"]}
        assert domaines_source.issubset(domaines)

        mentions_par_nom: dict[str, list[Mention]] = {}
        for mention in mentions:
            mentions_par_nom.setdefault(_normaliser(mention.nom), []).append(mention)

        for nom in {ligne["mention"] for ligne in payload["formations"]}:
            variantes = mentions_par_nom.get(_normaliser(nom), [])
            assert variantes, f"Mention source absente de la base : {nom}"
            assert any(mention.domaine_id is not None for mention in variantes), (
                f"Mention source sans Domaine après synchronisation : {nom}"
            )

        uto = next(
            u for u in session.exec(select(Universite)).all()
            if _normaliser(u.nom) == "universite de toamasina"
        )

        facs = {
            _normaliser(f.nom): f
            for f in session.exec(select(Faculte).where(Faculte.universite_id == uto.id)).all()
        }
        filieres = session.exec(
            select(Filiere).where(
                Filiere.faculte_id.in_([f.id for f in facs.values()])
            )
        ).all()
        programmes = session.exec(
            select(ProgrammeUniversitaire).where(
                ProgrammeUniversitaire.universite_id == uto.id,
                ProgrammeUniversitaire.est_active.is_(True),
            )
        ).all()

        # Le référentiel publié est réconcilié strictement par l'application.
        # Seules les lignes vérifiées/confirmées de la source sont publiables.
        attendues = [
            ligne for ligne in payload["formations"]
            if _normaliser(ligne.get("statut")) in {"verifie", "confirme"}
            and _normaliser(ligne["type"]) != _normaliser("Tronc commun")
        ]

        # Le smoke test vérifie ici le contrat opérationnel : il existe des
        # offres actives pour Toamasina et chaque offre pointe vers une Filiere
        # réellement rattachée à une composante de cette université.
        assert attendues
        assert programmes
        filiere_ids = {fil.id for fil in filieres}
        assert all(programme.filiere_id in filiere_ids for programme in programmes)

        # Contrôle aussi le catalogue scolaire seedé par la migration :
        # Sciences naturelles reste le libellé du collège, lié à la source
        # officielle 6e 2024-2025, sans être confondu avec SVT au lycée.
        referentiel_scolaire = session.exec(
            select(ReferentielScolaire).where(
                ReferentielScolaire.code == "MEN-RAPS-2024-2025-initial"
            )
        ).one()
        sixieme = session.exec(
            select(NiveauScolaire).where(
                NiveauScolaire.referentiel_id == referentiel_scolaire.id,
                NiveauScolaire.code == "6E",
            )
        ).one()
        sciences_naturelles = session.exec(
            select(MatiereScolaire).where(MatiereScolaire.code == "SCIENCES_NATURELLES")
        ).one()
        association_sciences = session.exec(
            select(ProgrammeMatiereScolaire).where(
                ProgrammeMatiereScolaire.referentiel_id == referentiel_scolaire.id,
                ProgrammeMatiereScolaire.niveau_id == sixieme.id,
                ProgrammeMatiereScolaire.option_id.is_(None),
                ProgrammeMatiereScolaire.matiere_id == sciences_naturelles.id,
            )
        ).one()
        assert association_sciences.statut_validation == "verifie"
        assert association_sciences.source_officielle.startswith(
            "https://www.education.gov.mg/wp-content/uploads/2024/09/"
        )
        assert "RAPS-6%C3%A8me_2024_2025.pdf" in association_sciences.source_officielle

        # Les séries A/C/L ne doivent pas rester entièrement inutilisables :
        # ces quelques matières sont activées seulement si leur PDF précis
        # confirme directement le contenu.
        for code_niveau, code_serie, code_matiere, fichier in [
            ("1ERE", "A", "MATHEMATIQUES", "RAPS-1%C3%A8re-A_2024_2025.pdf"),
            ("1ERE", "C", "MATHEMATIQUES", "RAPS-1%C3%A8re-C_2024_2025.pdf"),
            ("TERM", "C", "PHILOSOPHIE", "RAPS-Tle-C_2024_2025.pdf"),
            ("1ERE", "L", "FRANCAIS", "RAPE-T11-L_2024_2025.pdf"),
        ]:
            niveau_cible = session.exec(
                select(NiveauScolaire).where(
                    NiveauScolaire.referentiel_id == referentiel_scolaire.id,
                    NiveauScolaire.code == code_niveau,
                )
            ).one()
            serie = session.exec(
                select(OptionScolaire).where(
                    OptionScolaire.referentiel_id == referentiel_scolaire.id,
                    OptionScolaire.niveau_id == niveau_cible.id,
                    OptionScolaire.code == code_serie,
                    OptionScolaire.parent_option_id.is_(None),
                )
            ).one()
            matiere_cible = session.exec(
                select(MatiereScolaire).where(MatiereScolaire.code == code_matiere)
            ).one()
            association = session.exec(
                select(ProgrammeMatiereScolaire).where(
                    ProgrammeMatiereScolaire.referentiel_id == referentiel_scolaire.id,
                    ProgrammeMatiereScolaire.niveau_id == niveau_cible.id,
                    ProgrammeMatiereScolaire.option_id == serie.id,
                    ProgrammeMatiereScolaire.matiere_id == matiere_cible.id,
                )
            ).one()
            assert association.statut_validation == "verifie"
            assert fichier in association.source_officielle

        createur = session.exec(select(Utilisateur)).first()
        if createur is None:
            createur = Utilisateur(
                nom="Smoke PostgreSQL",
                telephone="0320000001",
                mot_de_passe_hash="smoke-only",
            )
            session.add(createur)
            session.commit()
            session.refresh(createur)

        filiere_smoke = next(
            (fil for fil in filieres if _normaliser(fil.niveau) == "m1"),
            None,
        )
        assert filiere_smoke is not None, "Aucune Filiere M1 n'est disponible apres synchronisation."
        smoke = CercleEtude(
            nom="Smoke PostgreSQL — parcours M1 Toamasina",
            createur_id=createur.id,
            mention_id=filiere_smoke.mention_id,
            filiere_id=filiere_smoke.id,
            niveau="M1",
        )
        session.add(smoke)
        session.commit()

        rapport_second_passage = importer(str(SOURCE))
        assert rapport_second_passage.domaines_crees == []
        assert rapport_second_passage.mentions_creees == []
        assert rapport_second_passage.filieres_creees == []
        assert rapport_second_passage.programmes_crees == 0

        nb_domaines = session.exec(select(func.count()).select_from(Domaine)).one()
        nb_mentions = session.exec(select(func.count()).select_from(Mention)).one()

        bucket = session.connection().exec_driver_sql(
            "SELECT public, file_size_limit, allowed_mime_types "
            "FROM storage.buckets WHERE id = 'documents'"
        ).one()
        assert bucket[0] is False
        assert bucket[1] == 20 * 1024 * 1024
        assert "application/pdf" in bucket[2]

    with TestClient(app) as client:
        page = client.get("/cercles", params={"q": "Smoke PostgreSQL"})
        assert page.status_code == 200
        assert "Smoke PostgreSQL — parcours M1 Toamasina" in page.text

    assert nb_domaines >= len(domaines_source)
    assert nb_mentions >= len(mentions_par_nom)



@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith(("postgresql://", "postgresql+psycopg2://")),
    reason="Test de permissions réservé à PostgreSQL",
)
def test_rls_auto_enable_acl_migration_restricts_api_roles_and_keeps_ddl_trigger():
    """La migration retire les RPC grants sans casser l'événement DDL."""
    import importlib.util

    from app.database import engine

    migration_path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "f3a9c1d8e742_restreindre_execute_rls_auto_enable.py"
    )
    spec = importlib.util.spec_from_file_location("migration_rls_auto_enable_acl", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            # Le test s'exécute dans une transaction toujours annulée. Il ne
            # modifie donc ni les rôles ni les objets persistants de la base.
            is_superuser = connection.exec_driver_sql(
                "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
            ).scalar()
            if not is_superuser:
                pytest.skip("Le smoke PostgreSQL doit pouvoir créer un event trigger.")

            function_exists = connection.exec_driver_sql(
                "SELECT to_regprocedure('public.rls_auto_enable()') IS NOT NULL"
            ).scalar()
            if function_exists:
                pytest.skip("Fonction déjà présente : ne pas modifier une configuration Supabase réelle.")

            trigger_exists = connection.exec_driver_sql(
                "SELECT EXISTS (SELECT 1 FROM pg_event_trigger "
                "WHERE evtname = '_mitaridala_test_rls_auto_enable')"
            ).scalar()
            if trigger_exists:
                pytest.skip("Le déclencheur de test existe déjà.")

            for role in ("anon", "authenticated", "service_role"):
                exists = connection.execute(
                    __import__("sqlalchemy").text(
                        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :role)"
                    ),
                    {"role": role},
                ).scalar()
                if not exists:
                    connection.exec_driver_sql(f'CREATE ROLE "{role}" NOLOGIN')

            connection.exec_driver_sql(
                """
                CREATE FUNCTION public.rls_auto_enable()
                RETURNS event_trigger
                LANGUAGE plpgsql
                SECURITY DEFINER
                SET search_path TO 'pg_catalog'
                AS $function$
                DECLARE cmd record;
                BEGIN
                  FOR cmd IN
                    SELECT *
                    FROM pg_event_trigger_ddl_commands()
                    WHERE command_tag IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
                      AND object_type IN ('table', 'partitioned table')
                  LOOP
                    IF cmd.schema_name = 'public'
                       AND cmd.object_identity = 'public._mitaridala_rls_auto_enable_probe' THEN
                      EXECUTE
                        'ALTER TABLE public._mitaridala_rls_auto_enable_probe '
                        'ENABLE ROW LEVEL SECURITY';
                    END IF;
                  END LOOP;
                END;
                $function$;
                """
            )
            connection.exec_driver_sql(
                "CREATE EVENT TRIGGER _mitaridala_test_rls_auto_enable "
                "ON ddl_command_end EXECUTE FUNCTION public.rls_auto_enable()"
            )
            connection.exec_driver_sql(
                "GRANT EXECUTE ON FUNCTION public.rls_auto_enable() "
                "TO PUBLIC, anon, authenticated, service_role"
            )

            migration._revoquer_execution(connection)

            permissions = connection.exec_driver_sql(
                """
                SELECT
                  has_function_privilege('anon', 'public.rls_auto_enable()', 'EXECUTE'),
                  has_function_privilege('authenticated', 'public.rls_auto_enable()', 'EXECUTE'),
                  has_function_privilege('service_role', 'public.rls_auto_enable()', 'EXECUTE')
                """
            ).one()
            assert tuple(permissions) == (False, False, False)

            connection.exec_driver_sql(
                "CREATE TABLE public._mitaridala_rls_auto_enable_probe (id integer)"
            )
            rls_enabled = connection.exec_driver_sql(
                "SELECT relrowsecurity FROM pg_class "
                "WHERE oid = 'public._mitaridala_rls_auto_enable_probe'::regclass"
            ).scalar()
            assert rls_enabled is True
        finally:
            transaction.rollback()


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith(("postgresql://", "postgresql+psycopg2://")),
    reason="Contrôle des privilèges Data API réservé à PostgreSQL",
)
def test_postgres_api_roles_have_no_blanket_table_sequence_or_default_grants():
    """Les rôles Data API ne peuvent pas contourner les politiques RLS."""
    from sqlalchemy import text

    from app.database import engine

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            existing = connection.execute(
                text(
                    """
                    SELECT
                      COUNT(*) FILTER (
                        WHERE has_table_privilege('anon', c.oid, 'SELECT')
                           OR has_table_privilege('anon', c.oid, 'INSERT')
                           OR has_table_privilege('anon', c.oid, 'UPDATE')
                           OR has_table_privilege('anon', c.oid, 'DELETE')
                           OR has_table_privilege('anon', c.oid, 'TRUNCATE')
                           OR has_table_privilege('anon', c.oid, 'REFERENCES')
                           OR has_table_privilege('anon', c.oid, 'TRIGGER')
                      ) AS anon_tables,
                      COUNT(*) FILTER (
                        WHERE has_table_privilege('authenticated', c.oid, 'SELECT')
                           OR has_table_privilege('authenticated', c.oid, 'INSERT')
                           OR has_table_privilege('authenticated', c.oid, 'UPDATE')
                           OR has_table_privilege('authenticated', c.oid, 'DELETE')
                           OR has_table_privilege('authenticated', c.oid, 'TRUNCATE')
                           OR has_table_privilege('authenticated', c.oid, 'REFERENCES')
                           OR has_table_privilege('authenticated', c.oid, 'TRIGGER')
                      ) AS authenticated_tables
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
                    """
                )
            ).one()
            assert existing.anon_tables == 0
            assert existing.authenticated_tables == 0

            sequence_privileges = connection.execute(
                text(
                    """
                    SELECT
                      COUNT(*) FILTER (
                        WHERE has_sequence_privilege('anon', c.oid, 'USAGE')
                           OR has_sequence_privilege('anon', c.oid, 'SELECT')
                           OR has_sequence_privilege('anon', c.oid, 'UPDATE')
                      ) AS anon_sequences,
                      COUNT(*) FILTER (
                        WHERE has_sequence_privilege('authenticated', c.oid, 'USAGE')
                           OR has_sequence_privilege('authenticated', c.oid, 'SELECT')
                           OR has_sequence_privilege('authenticated', c.oid, 'UPDATE')
                      ) AS authenticated_sequences
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relkind = 'S'
                    """
                )
            ).one()
            assert sequence_privileges.anon_sequences == 0
            assert sequence_privileges.authenticated_sequences == 0

            defaults = connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM pg_default_acl d
                    CROSS JOIN LATERAL aclexplode(d.defaclacl) a
                    JOIN pg_roles r ON r.oid = a.grantee
                    WHERE d.defaclrole = (
                        SELECT oid FROM pg_roles WHERE rolname = 'postgres'
                      )
                      AND d.defaclnamespace = 'public'::regnamespace
                      AND r.rolname IN ('anon', 'authenticated')
                    """
                )
            ).scalar_one()
            assert defaults == 0

            # DDL de test transactionnel : confirme que les prochains objets
            # n'héritent pas de droits de données ou d'exécution RPC.
            connection.exec_driver_sql(
                "CREATE TABLE public._mitaridala_api_acl_probe "
                "(id BIGSERIAL PRIMARY KEY, contenu TEXT)"
            )
            connection.exec_driver_sql(
                """
                CREATE FUNCTION public._mitaridala_api_acl_probe_fn()
                RETURNS integer
                LANGUAGE sql
                AS $$ SELECT 1 $$
                """
            )

            nouveaux_objets = connection.execute(
                text(
                    """
                    SELECT
                      has_table_privilege('anon', 'public._mitaridala_api_acl_probe', 'SELECT') AS anon_select,
                      has_table_privilege('authenticated', 'public._mitaridala_api_acl_probe', 'TRUNCATE') AS auth_truncate,
                      has_sequence_privilege('anon', 'public._mitaridala_api_acl_probe_id_seq', 'USAGE') AS anon_sequence_usage,
                      has_function_privilege('anon', 'public._mitaridala_api_acl_probe_fn()', 'EXECUTE') AS anon_function_execute,
                      has_function_privilege('authenticated', 'public._mitaridala_api_acl_probe_fn()', 'EXECUTE') AS auth_function_execute,
                      has_table_privilege('postgres', 'public.document', 'SELECT') AS app_owner_select,
                      has_table_privilege('service_role', 'public.document', 'SELECT') AS service_role_select
                    """
                )
            ).one()
            assert nouveaux_objets.anon_select is False
            assert nouveaux_objets.auth_truncate is False
            assert nouveaux_objets.anon_sequence_usage is False
            assert nouveaux_objets.anon_function_execute is False
            assert nouveaux_objets.auth_function_execute is False
            assert nouveaux_objets.app_owner_select is True
            assert nouveaux_objets.service_role_select is True
        finally:
            transaction.rollback()


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith(("postgresql://", "postgresql+psycopg2://")),
    reason="Index de clés étrangères réservés à PostgreSQL",
)
def test_postgres_indexes_all_uncovered_foreign_keys():
    """Vérifie que la migration fournit un index B-tree pour chaque alerte suivie."""
    from sqlalchemy import text

    from app.database import engine

    expected = [
        ("ix_fk_abonnement_utilisateur_id", "abonnement", "utilisateur_id"),
        ("ix_fk_abonnementetudiant_valide_par_admin_id", "abonnementetudiant", "valide_par_admin_id"),
        ("ix_fk_autorisationecrituretableau_utilisateur_id", "autorisationecrituretableau", "utilisateur_id"),
        ("ix_fk_codereinitialisationmotdepasse_utilisateur_id", "codereinitialisationmotdepasse", "utilisateur_id"),
        ("ix_fk_codesecours2fa_utilisateur_id", "codesecours2fa", "utilisateur_id"),
        ("ix_fk_consultationdocument_document_id", "consultationdocument", "document_id"),
        ("ix_fk_consultationdocument_utilisateur_id", "consultationdocument", "utilisateur_id"),
        ("ix_fk_cours_professeur_id", "cours", "professeur_id"),
        ("ix_fk_demandechangementfiliere_ancienne_filiere_id", "demandechangementfiliere", "ancienne_filiere_id"),
        ("ix_fk_demandechangementfiliere_nouvelle_filiere_id", "demandechangementfiliere", "nouvelle_filiere_id"),
        ("ix_fk_demandechangementfiliere_traite_par_id", "demandechangementfiliere", "traite_par_id"),
        ("ix_fk_demandechangementfiliere_utilisateur_id", "demandechangementfiliere", "utilisateur_id"),
        ("ix_fk_demandechangementfiliere_nouvelle_faculte_id", "demandechangementfiliere", "nouvelle_faculte_id"),
        ("ix_fk_demandechangementfiliere_nouvelle_mention_id", "demandechangementfiliere", "nouvelle_mention_id"),
        ("ix_fk_devoir_cours_id", "devoir", "cours_id"),
        ("ix_fk_document_fiche_validee_par_id", "document", "fiche_validee_par_id"),
        ("ix_fk_document_filiere_id", "document", "filiere_id"),
        ("ix_fk_document_uploader_id", "document", "uploader_id"),
        ("ix_fk_evenementtableaublanc_utilisateur_id", "evenementtableaublanc", "utilisateur_id"),
        ("ix_fk_faq_cree_par_id", "faq", "cree_par_id"),
        ("ix_fk_filiere_faculte_id", "filiere", "faculte_id"),
        ("ix_fk_filiere_mention_id", "filiere", "mention_id"),
        ("ix_fk_inscriptioncours_utilisateur_id", "inscriptioncours", "utilisateur_id"),
        ("ix_fk_mention_domaine_id", "mention", "domaine_id"),
        ("ix_fk_notification_acteur_id", "notification", "acteur_id"),
        ("ix_fk_notification_cercle_id", "notification", "cercle_id"),
        ("ix_fk_notification_message_id", "notification", "message_id"),
        ("ix_fk_presenceseance_seance_id", "presenceseance", "seance_id"),
        ("ix_fk_presenceseance_utilisateur_id", "presenceseance", "utilisateur_id"),
        ("ix_fk_programmeuniversitaire_filiere_id", "programmeuniversitaire", "filiere_id"),
        ("ix_fk_referentielscolaire_valide_par_id", "referentielscolaire", "valide_par_id"),
        ("ix_fk_rendudevoir_utilisateur_id", "rendudevoir", "utilisateur_id"),
        ("ix_fk_reponsefeedback_admin_id", "reponsefeedback", "admin_id"),
        ("ix_fk_seance_cours_id", "seance", "cours_id"),
        ("ix_fk_sessiontuteur_utilisateur_id", "sessiontuteur", "utilisateur_id"),
        ("ix_fk_signalementquestionquiz_signale_par_id", "signalementquestionquiz", "signale_par_id"),
        ("ix_fk_signalementquestionquiz_tentative_id", "signalementquestionquiz", "tentative_id"),
        ("ix_fk_utilisateur_mention_id", "utilisateur", "mention_id"),
        ("ix_fk_utilisateur_universite_id", "utilisateur", "universite_id"),
        ("ix_fk_utilisateur_verification_enseignant_par_id", "utilisateur", "verification_enseignant_par_id"),
        ("ix_fk_utilisateur_filiere_id", "utilisateur", "filiere_id"),
    ]
    names = [item[0] for item in expected]

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT indexname, tablename, indexdef "
                "FROM pg_indexes "
                "WHERE schemaname = 'public' AND indexname = ANY(:names)"
            ),
            {"names": names},
        ).all()

    actual = {row.indexname: row for row in rows}
    missing = sorted(set(names) - set(actual))
    assert not missing, f"Index de clés étrangères absents : {missing}"

    mismatched = [
        (name, table, column, actual[name].tablename, actual[name].indexdef)
        for name, table, column in expected
        if actual[name].tablename != table
        or f"({column})" not in actual[name].indexdef
        or " USING btree " not in actual[name].indexdef
    ]
    assert not mismatched, f"Index de clés étrangères incorrects : {mismatched}"


@pytest.mark.skipif(
    os.environ.get("MITARIDALA_MIGRATION_CONCURRENCY_SMOKE") != "1"
    or not os.environ.get("DATABASE_URL", "").startswith(
        ("postgresql://", "postgresql+psycopg2://")
    ),
    reason="Test concurrent réservé à la base PostgreSQL jetable de CI",
)
def test_postgres_concurrent_alembic_upgrades_are_serialized():
    """Rejoue deux upgrades simultanés depuis l'ancêtre commun des dernières migrations."""
    from concurrent.futures import ThreadPoolExecutor
    import subprocess
    import sys

    from sqlalchemy import text

    from app.database import engine

    env = os.environ.copy()
    alembic = [sys.executable, "-m", "alembic"]

    with engine.connect() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM public.alembic_version")
        ).scalar_one()
    assert revision == "c2f7a9e4b1d6", (
        "Le test concurrent doit démarrer sur la tête actuelle du graphe Alembic."
    )

    downgrade = subprocess.run(
        [*alembic, "downgrade", "f6b1a2c9d4e7"],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert downgrade.returncode == 0, (
        "Le retour contrôlé au parent de la migration a échoué :\n"
        f"{downgrade.stdout}\n{downgrade.stderr}"
    )

    def upgrade():
        return subprocess.run(
            [*alembic, "upgrade", "head"],
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

    # Two distinct processes have separate DB connections, like overlapping
    # Render instances starting the same release at the same time.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: upgrade(), range(2)))

    failures = [
        f"exit={result.returncode}\n{result.stdout}\n{result.stderr}"
        for result in results
        if result.returncode != 0
    ]
    assert not failures, "Les upgrades Alembic concurrents ont échoué :\n" + "\n---\n".join(failures)

    with engine.connect() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM public.alembic_version")
        ).scalar_one()
        index_count = connection.execute(
            text(
                "SELECT COUNT(*) FROM pg_indexes "
                "WHERE schemaname = 'public' AND indexname LIKE 'ix_fk_%'"
            )
        ).scalar_one()

    assert revision == "9f0b1c2d3e4f"
    assert index_count == 41


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith(
        ("postgresql://", "postgresql+psycopg2://")
    ),
    reason="Contrôle des index uniques réservé à PostgreSQL",
)
def test_postgres_duplicate_unique_code_indexes_are_removed():
    """Le UNIQUE constraint couvre déjà le code; pas de deuxième index identique."""
    from sqlalchemy import text

    from app.database import engine

    redundant = [
        ("etablissementscolaire", "ix_etablissementscolaire_code", "uq_etablissementscolaire_code"),
        ("matierescolaire", "ix_matierescolaire_code", "uq_matierescolaire_code"),
        ("referentielscolaire", "ix_referentielscolaire_code", "uq_referentielscolaire_code"),
    ]

    with engine.connect() as connection:
        remaining_indexes = connection.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' AND indexname = ANY(:names)"
            ),
            {"names": [item[1] for item in redundant]},
        ).scalars().all()
        assert not remaining_indexes, (
            "Index uniques redondants encore présents : "
            f"{sorted(remaining_indexes)}"
        )

        constraints = connection.execute(
            text(
                "SELECT c.relname AS table_name, con.conname "
                "FROM pg_constraint con "
                "JOIN pg_class c ON c.oid = con.conrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND con.contype = 'u' "
                "AND con.conname = ANY(:names)"
            ),
            {"names": [item[2] for item in redundant]},
        ).all()

    actual = {(row.table_name, row.conname) for row in constraints}
    expected = {(table, constraint) for table, _index, constraint in redundant}
    assert actual == expected, (
        "Les contraintes UNIQUE protégées ne correspondent pas aux attentes : "
        f"attendu={sorted(expected)}, obtenu={sorted(actual)}"
    )


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith(("postgresql://", "postgresql+psycopg2://")),
    reason="Parcours complet fiche documentaire réservé à PostgreSQL",
)
def test_postgres_fiche_revision_de_approbation_a_export_prive_personnalise(monkeypatch):
    """Exerce le parcours critique sur PostgreSQL sans appel IA ni fichier réel."""
    from app.database import engine

    suffixe = str(int.from_bytes(secrets.token_bytes(6), "big"))[-10:]
    reference = f"TEST-FICHE-E2E-{suffixe}"
    telephones = [f"034{suffixe}", f"032{suffixe}", f"033{suffixe}"]
    ids_utilisateurs = []
    document_id = None
    source_texte = (
        "Matrices et déterminants. Une matrice est un tableau rectangulaire de coefficients. "
        "Le déterminant d'une matrice carrée permet notamment d'étudier son inversibilité. "
        "Pour une matrice deux par deux, le déterminant se calcule par ad moins bc. "
        "Le produit AB existe lorsque le nombre de colonnes de A égale le nombre de lignes de B. "
        "On peut utiliser des exemples corrigés pour vérifier les calculs. "
    ) * 3

    contenu_fiche = {
        "resume": "Le cours présente les matrices, les déterminants et les produits matriciels.",
        "objectifs": ["Reconnaître les dimensions d'une matrice", "Calculer un déterminant", "Vérifier un produit matriciel"],
        "notions": [
            {"titre": "Matrice", "explication": "Une matrice est un tableau rectangulaire de coefficients.", "exemple": "Une matrice 2 × 2 a quatre coefficients."},
            {"titre": "Déterminant", "explication": r"Pour une matrice 2 × 2, \(\det(A)=ad-bc\).", "exemple": "Pour [[2,1],[3,4]], le déterminant vaut 5."},
            {"titre": "Produit matriciel", "explication": "Les dimensions internes doivent coïncider.", "exemple": "Une matrice 2 × 3 peut multiplier une matrice 3 × 1."},
        ],
        "erreurs_frequentes": [
            {"erreur": "Inverser les termes du déterminant", "pourquoi": "Le signe peut changer.", "comment_eviter": "Appliquer la formule ad - bc dans le même ordre."},
        ],
        "outils_a_retenir": [
            {"titre": "Déterminant 2 × 2", "contenu": r"\(ad-bc\)", "explication": "Multiplier les termes diagonaux puis soustraire les deux produits."},
        ],
        "exercices": [
            {"enonce": "Calcule le déterminant de [[2,1],[3,4]].", "difficulte": "Facile", "indice": "Calcule ad - bc.", "correction": "2×4 - 1×3 = 5.", "notion": "Déterminant"},
            {"enonce": "Vérifie les dimensions avant le produit AB.", "difficulte": "Moyen", "indice": "Compare les dimensions internes.", "correction": "Les colonnes de A doivent égaler les lignes de B.", "notion": "Produit matriciel"},
            {"enonce": "Que signifie un déterminant nul ?", "difficulte": "Moyen", "indice": "Pense à l'inversibilité.", "correction": "La matrice carrée n'est pas inversible.", "notion": "Déterminant"},
        ],
        "points_a_retravailler": ["Vérifier les dimensions avant un produit matriciel."],
        "plan_revision": [
            {"moment": "Aujourd'hui", "action": "Revoir la notion prioritaire puis refaire un exercice sans regarder l'indice."},
            {"moment": "Dans 3 jours", "action": "Répondre à un quiz avec des questions nouvelles."},
            {"moment": "Dans 7 jours", "action": "Vérifier la rétention avec une application différente."},
        ],
        "auto_evaluation": [
            {"question": "Quelle formule calcule le déterminant 2 × 2 ?", "reponse": "ad - bc."},
            {"question": "Quelle condition vérifie-t-on pour le produit AB ?", "reponse": "Le nombre de colonnes de A égale le nombre de lignes de B."},
            {"question": "Que signifie un déterminant nul pour une matrice carrée ?", "reponse": "La matrice n'est pas inversible."},
        ],
        "limites_sources": "Fiche générée depuis le texte extrait du cours approuvé.",
    }

    try:
        with Session(engine) as session:
            filiere = session.exec(
                select(Filiere).where(Filiere.niveau == "M1").limit(1)
            ).first()
            assert filiere is not None, "Le smoke PostgreSQL doit avoir synchronisé une filière M1."

            admin = Utilisateur(
                nom=f"Admin smoke fiche {suffixe}",
                telephone=telephones[0],
                mot_de_passe_hash="smoke-only",
                role=RoleUtilisateur.ADMIN,
            )
            etudiant_a = Utilisateur(
                nom=f"Étudiante A smoke {suffixe}",
                telephone=telephones[1],
                mot_de_passe_hash="smoke-only",
                role=RoleUtilisateur.ETUDIANT,
                niveau="M1",
            )
            etudiant_b = Utilisateur(
                nom=f"Étudiant B smoke {suffixe}",
                telephone=telephones[2],
                mot_de_passe_hash="smoke-only",
                role=RoleUtilisateur.ETUDIANT,
                niveau="M1",
            )
            session.add_all([admin, etudiant_a, etudiant_b])
            session.commit()
            session.refresh(admin)
            session.refresh(etudiant_a)
            session.refresh(etudiant_b)
            ids_utilisateurs.extend([admin.id, etudiant_a.id, etudiant_b.id])

            document = Document(
                reference=reference,
                titre="Matrices et déterminants — scénario PostgreSQL",
                matiere="Mathématiques",
                type_document=TypeDocument.COURS,
                annee=2026,
                filiere_id=filiere.id,
                portee_academique="universitaire",
                uploader_id=etudiant_a.id,
                chemin_fichier=f"/tmp/{reference}.pdf",
                statut=StatutDocument.EN_ATTENTE,
            )
            session.add(document)
            session.commit()
            session.refresh(document)
            document_id = document.id

            session.add_all([
                ProgressionNotion(
                    utilisateur_id=etudiant_a.id,
                    matiere="Mathématiques",
                    niveau=filiere.niveau or "M1",
                    notion="Déterminant",
                    nb_questions=8,
                    nb_reussites=2,
                    nb_erreurs=6,
                    score_maitrise=25,
                    confiance_maitrise=30,
                    maitrise_confirmee=False,
                ),
                ProgressionNotion(
                    utilisateur_id=etudiant_b.id,
                    matiere="Mathématiques",
                    niveau=filiere.niveau or "M1",
                    notion="Produit matriciel",
                    nb_questions=10,
                    nb_reussites=9,
                    nb_erreurs=1,
                    score_maitrise=88,
                    confiance_maitrise=90,
                    maitrise_confirmee=True,
                ),
            ])
            session.commit()

        notifications_file = []
        monkeypatch.setattr(
            ai_queue,
            "notifier_tache",
            lambda task_id: notifications_file.append(task_id) or True,
        )
        # La route reçoit une identité minimale détachée ; on ne réutilise pas
        # un modèle SQL expiré après la fermeture de sa session de création.
        current = {"user": SimpleNamespace(id=ids_utilisateurs[0], role=RoleUtilisateur.ADMIN)}
        monkeypatch.setattr(
            documents_router,
            "utilisateur_courant",
            lambda _request, _session: current["user"],
        )

        # 1. Approbation réelle via la route : la génération est mise en file,
        # mais l'action d'administration ne fait aucun appel IA synchrone.
        with Session(engine) as session:
            response = documents_router.approuver_document(
                SimpleNamespace(session={}), document_id, session, _csrf=None
            )
            assert response.status_code == 303
            document = session.get(Document, document_id)
            assert document.statut == StatutDocument.APPROUVE

        with Session(engine) as session:
            fiche = session.exec(
                select(FicheRevisionDocument).where(FicheRevisionDocument.document_id == document_id)
            ).first()
            assert fiche is not None
            assert fiche.statut == StatutFicheRevisionDocument.EN_ATTENTE
            taches = session.exec(
                select(TacheIA).where(
                    TacheIA.type_tache == ai_queue.TYPE_FICHE_REVISION_DOCUMENT,
                    TacheIA.fiche_revision_document_id == fiche.id,
                )
            ).all()
            assert len(taches) == 1
            task_id = taches[0].id
            assert task_id in notifications_file

        # 2. Le worker revendique puis traite la tâche durable. Seule la lecture
        # du fichier et le fournisseur IA sont simulés ; la persistance finale
        # et les transitions de la file restent réelles dans PostgreSQL.
        @contextmanager
        def faux_fichier(_reference):
            yield Path(f"/tmp/{reference}.pdf")

        contextes_generes = []
        monkeypatch.setattr(course_revision, "ouvrir_fichier_local", faux_fichier)
        monkeypatch.setattr(course_revision, "extraire_texte", lambda _path: source_texte)

        def generer_fiche(contexte, mode_document=False):
            contextes_generes.append((contexte, mode_document))
            return json.loads(json.dumps(contenu_fiche, ensure_ascii=False))

        monkeypatch.setattr(course_revision, "_generer_contenu_ia", generer_fiche)

        tache = ai_queue.prendre_tache(task_id)
        assert tache is not None
        assert tache.statut == StatutTacheIA.EN_COURS
        ai_worker.traiter_tache(tache)
        ai_queue.terminer_tache(task_id)

        with Session(engine) as session:
            fiche = session.exec(
                select(FicheRevisionDocument).where(FicheRevisionDocument.document_id == document_id)
            ).one()
            tache_finale = session.get(TacheIA, task_id)
            assert tache_finale.statut == StatutTacheIA.TERMINEE
            assert fiche.statut == StatutFicheRevisionDocument.TERMINEE
            source_json_initiale = fiche.contenu_json
            source = json.loads(source_json_initiale)
            assert source["resume"] == contenu_fiche["resume"]
            assert json.loads(fiche.sources_json)["reference"] == reference
            assert contextes_generes and contextes_generes[0][1] is True
            assert reference in contextes_generes[0][0]["source_document"]["reference"]
            assert len(contextes_generes[0][0]["source_document"]["contenu_extrait"]) >= 250
            assert session.exec(
                select(func.count()).select_from(Notification).where(
                    Notification.destinataire_id == ids_utilisateurs[1],
                    Notification.type_notification == TypeNotification.FICHE_REVISION_DOCUMENT_PRETE,
                )
            ).one() == 1

        # 3. Le téléchargement anonyme est refusé avant lecture de la fiche.
        current["user"] = None
        with Session(engine) as session:
            reponse_anonyme = documents_router.telecharger_fiche_revision_document(
                SimpleNamespace(session={}), document_id, "pdf", session
            )
        assert reponse_anonyme.status_code == 303
        assert reponse_anonyme.headers["location"] == "/connexion"

        # 4. L'affichage construit un profil privé pour chaque compte sans muter
        # le contenu source commun sauvegardé dans PostgreSQL.
        contextes_page = []
        monkeypatch.setattr(
            documents_router,
            "templates",
            SimpleNamespace(
                TemplateResponse=lambda _request, _template, contexte:
                    (contextes_page.append(contexte) or SimpleNamespace(status_code=200))
            ),
        )
        for utilisateur_id in ids_utilisateurs[1:]:
            with Session(engine) as session:
                current["user"] = session.get(Utilisateur, utilisateur_id)
                response = documents_router.consulter_fiche_revision_document(
                    SimpleNamespace(session={}), document_id, session
                )
                assert response.status_code == 200

        profils_page = [c["fiche_contenu"]["profil_personnalise"] for c in contextes_page]
        assert profils_page[0]["priorites"][0]["notion"] == "Déterminant"
        assert profils_page[1]["priorites"][0]["notion"] == "Produit matriciel"
        assert profils_page[0]["priorites"][0]["notion"] != profils_page[1]["priorites"][0]["notion"]

        # 5. PDF et DOCX doivent recevoir le profil propre au compte connecté
        # et renvoyer des pièces jointes réellement valides.
        exports = []
        generer_pdf_original = course_revision.generer_pdf
        generer_docx_original = course_revision.generer_docx

        def pdf_personnalise(fiche, cours, seance, nom_etudiant):
            exports.append(("pdf", nom_etudiant, fiche["profil_personnalise"]["priorites"][0]["notion"]))
            return generer_pdf_original(fiche, cours, seance, nom_etudiant)

        def docx_personnalise(fiche, cours, seance, nom_etudiant):
            exports.append(("docx", nom_etudiant, fiche["profil_personnalise"]["priorites"][0]["notion"]))
            return generer_docx_original(fiche, cours, seance, nom_etudiant)

        monkeypatch.setattr(course_revision, "generer_pdf", pdf_personnalise)
        monkeypatch.setattr(course_revision, "generer_docx", docx_personnalise)

        for utilisateur_id in ids_utilisateurs[1:]:
            for format_fichier, prefixe in (("pdf", b"%PDF"), ("docx", b"PK")):
                with Session(engine) as session:
                    current["user"] = session.get(Utilisateur, utilisateur_id)
                    response = documents_router.telecharger_fiche_revision_document(
                        SimpleNamespace(session={}), document_id, format_fichier, session
                    )
                assert response.status_code == 200
                assert response.body.startswith(prefixe)
                assert response.headers["cache-control"] == "private, no-store"
                assert response.headers["x-content-type-options"] == "nosniff"

        assert ("pdf", f"Étudiante A smoke {suffixe}", "Déterminant") in exports
        assert ("docx", f"Étudiante A smoke {suffixe}", "Déterminant") in exports
        assert ("pdf", f"Étudiant B smoke {suffixe}", "Produit matriciel") in exports
        assert ("docx", f"Étudiant B smoke {suffixe}", "Produit matriciel") in exports

        with Session(engine) as session:
            fiche = session.exec(
                select(FicheRevisionDocument).where(FicheRevisionDocument.document_id == document_id)
            ).one()
            assert fiche.contenu_json == source_json_initiale

    finally:
        # Le smoke ne laisse aucune donnée de test dans la base utilisée par la CI.
        with Session(engine) as session:
            document = session.exec(
                select(Document).where(Document.reference == reference)
            ).first()
            fiche = None
            if document is not None:
                fiche = session.exec(
                    select(FicheRevisionDocument).where(
                        FicheRevisionDocument.document_id == document.id
                    )
                ).first()
            if fiche is not None:
                for tache in session.exec(
                    select(TacheIA).where(
                        TacheIA.fiche_revision_document_id == fiche.id
                    )
                ).all():
                    session.delete(tache)
                session.flush()
                session.delete(fiche)
                # Le modèle ne déclare pas de relation ORM pour cette paire ;
                # valider chaque niveau explicite évite un DELETE du document
                # avant celui de sa fiche sur PostgreSQL.
                session.flush()
            if document is not None:
                session.delete(document)
                session.flush()
            if ids_utilisateurs:
                for progression in session.exec(
                    select(ProgressionNotion).where(
                        ProgressionNotion.utilisateur_id.in_(ids_utilisateurs)
                    )
                ).all():
                    session.delete(progression)
                for notification in session.exec(
                    select(Notification).where(
                        or_(
                            Notification.destinataire_id.in_(ids_utilisateurs),
                            Notification.acteur_id.in_(ids_utilisateurs),
                        )
                    )
                ).all():
                    session.delete(notification)
                for utilisateur in session.exec(
                    select(Utilisateur).where(Utilisateur.id.in_(ids_utilisateurs))
                ).all():
                    session.delete(utilisateur)
            session.commit()
