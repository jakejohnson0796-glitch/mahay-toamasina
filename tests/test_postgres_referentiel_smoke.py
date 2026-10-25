"""
Smoke test PostgreSQL du référentiel académique Toamasina.

Ce test vérifie le chemin de production (PostgreSQL + Alembic + startup
FastAPI + import de la source issue du classeur fourni) sur une base neuve,
puis vérifie l'idempotence et une recherche HTTP réelle dans /cercles.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
import unicodedata

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select, func

from app.main import app
from app.models import (
    CercleEtude,
    Domaine,
    Faculte,
    Filiere,
    Mention,
    MatiereScolaire,
    NiveauScolaire,
    OptionScolaire,
    ProgrammeMatiereScolaire,
    ReferentielScolaire,
    ProgrammeUniversitaire,
    Universite,
    Utilisateur,
)
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
