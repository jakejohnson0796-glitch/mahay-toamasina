"""PostgreSQL integration test for the application-level tenant boundary.

This test runs only in the disposable PostgreSQL service created by GitHub
Actions. It does not claim that PostgreSQL RLS enforces tenant isolation:
the current backend connection is privileged and the tenant checks live in
app.institution_access. The test verifies those checks against real PostgreSQL
queries, including a deliberately inconsistent cross-tenant enrollment.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from sqlmodel import Session, create_engine

from app.institution_access import (
    ROLE_ETUDIANT,
    ROLE_PROFESSEUR,
    assurer_membre,
    est_inscrit_cours,
    lister_inscriptions_actives,
    peut_gerer_cours,
    peut_rejoindre_cours,
)
from app.models import (
    Cours,
    EtablissementPartenaire,
    InscriptionCours,
    RoleUtilisateur,
    Utilisateur,
)


@pytest.mark.postgres
def test_isolation_applicative_de_deux_etablissements_sur_postgresql() -> None:
    """A tenant B student must not enter or appear in tenant A course lists."""
    if os.getenv("MAHAY_POSTGRES_TENANT_AUTHORIZATION_SMOKE") != "1":
        pytest.skip("Réservé au PostgreSQL jetable du job postgres-smoke.")

    database_url = os.getenv("DATABASE_URL", "")
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        pytest.fail("DATABASE_URL doit pointer vers PostgreSQL.")
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("Refus d'exécuter ce test hors du PostgreSQL local et jetable de CI.")

    suffix = uuid4().hex[:12]
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            try:
                institution_a = EtablissementPartenaire(
                    nom=f"Université A {suffix}",
                    code=f"A-{suffix}",
                )
                institution_b = EtablissementPartenaire(
                    nom=f"Université B {suffix}",
                    code=f"B-{suffix}",
                )
                professor_a = Utilisateur(
                    nom=f"Professeur A {suffix}",
                    identifiant_connexion=f"prof-a-{suffix}",
                    mot_de_passe_hash="hash-test",
                    role=RoleUtilisateur.PROFESSEUR,
                )
                professor_b = Utilisateur(
                    nom=f"Professeur B {suffix}",
                    identifiant_connexion=f"prof-b-{suffix}",
                    mot_de_passe_hash="hash-test",
                    role=RoleUtilisateur.PROFESSEUR,
                )
                student_a = Utilisateur(
                    nom=f"Étudiant A {suffix}",
                    identifiant_connexion=f"etu-a-{suffix}",
                    mot_de_passe_hash="hash-test",
                    role=RoleUtilisateur.ETUDIANT,
                )
                student_b = Utilisateur(
                    nom=f"Étudiant B {suffix}",
                    identifiant_connexion=f"etu-b-{suffix}",
                    mot_de_passe_hash="hash-test",
                    role=RoleUtilisateur.ETUDIANT,
                )
                session.add_all(
                    [
                        institution_a,
                        institution_b,
                        professor_a,
                        professor_b,
                        student_a,
                        student_b,
                    ]
                )
                session.flush()

                assurer_membre(
                    session, institution_a.id, professor_a.id, ROLE_PROFESSEUR
                )
                assurer_membre(
                    session, institution_b.id, professor_b.id, ROLE_PROFESSEUR
                )
                membership_a = assurer_membre(
                    session, institution_a.id, student_a.id, ROLE_ETUDIANT
                )
                assurer_membre(
                    session, institution_b.id, student_b.id, ROLE_ETUDIANT
                )

                course_a = Cours(
                    nom=f"Cours A {suffix}",
                    matiere="Mathématiques",
                    niveau="L1",
                    professeur_id=professor_a.id,
                    institution_id=institution_a.id,
                )
                session.add(course_a)
                session.flush()

                # This inconsistent row simulates corrupted legacy data.
                # Application authorization must still reject student B.
                session.add_all(
                    [
                        InscriptionCours(
                            cours_id=course_a.id,
                            utilisateur_id=student_a.id,
                        ),
                        InscriptionCours(
                            cours_id=course_a.id,
                            utilisateur_id=student_b.id,
                        ),
                    ]
                )
                session.flush()

                assert peut_gerer_cours(session, course_a, professor_a)
                assert not peut_gerer_cours(session, course_a, professor_b)
                assert peut_rejoindre_cours(session, course_a, student_a)
                assert not peut_rejoindre_cours(session, course_a, student_b)
                assert est_inscrit_cours(session, course_a.id, student_a.id)
                assert not est_inscrit_cours(session, course_a.id, student_b.id)

                active_enrollments = lister_inscriptions_actives(
                    session, course_a.id
                )
                visible_student_ids = {
                    student.id for _enrollment, student in active_enrollments
                }
                assert visible_student_ids == {student_a.id}

                # Revocation must take effect in PostgreSQL-backed queries too.
                membership_a.est_actif = False
                session.add(membership_a)
                session.flush()
                assert not peut_rejoindre_cours(session, course_a, student_a)
                assert not est_inscrit_cours(session, course_a.id, student_a.id)
                assert lister_inscriptions_actives(session, course_a.id) == []
            finally:
                # Never leave fixture rows in the disposable database.
                session.rollback()
    finally:
        engine.dispose()
