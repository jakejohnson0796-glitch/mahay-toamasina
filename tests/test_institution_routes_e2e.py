"""Tests HTTP de bout en bout de la gestion des membres institutionnels."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from app.csrf import obtenir_jeton_csrf
from app.database import get_session
from app.institution_access import ROLE_RESPONSABLE, assurer_membre
from app.models import (
    EtablissementPartenaire,
    MembreEtablissement,
    RoleUtilisateur,
    Utilisateur,
)
from app.routers import institution_router


@pytest.fixture
def espace_http_institutionnel(monkeypatch):
    """Monte uniquement le routeur institutionnel sur une vraie stack HTTP."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        institution = EtablissementPartenaire(
            nom="Université de test",
            code="UNIV-HTTP",
        )
        responsable = Utilisateur(
            nom="Responsable de test",
            identifiant_connexion="RESP-HTTP-001",
            mot_de_passe_hash="hash-test",
            role=RoleUtilisateur.ETUDIANT,
        )
        etudiant = Utilisateur(
            nom="Étudiant cible",
            identifiant_connexion="ETU-HTTP-001",
            mot_de_passe_hash="hash-test",
            role=RoleUtilisateur.ETUDIANT,
        )
        session.add_all([institution, responsable, etudiant])
        session.commit()
        session.refresh(institution)
        session.refresh(responsable)
        session.refresh(etudiant)
        membre_responsable = assurer_membre(
            session, institution.id, responsable.id, ROLE_RESPONSABLE
        )
        session.commit()
        session.refresh(membre_responsable)

        institution_id = institution.id
        responsable_id = responsable.id
        etudiant_id = etudiant.id
        responsable_membre_id = membre_responsable.id

    identite = {"utilisateur_id": responsable_id}
    application = FastAPI()
    application.add_middleware(
        SessionMiddleware,
        secret_key="cle-de-session-reservee-aux-tests",
        https_only=False,
    )
    dossier_static = Path(institution_router.__file__).resolve().parents[1] / "static"
    application.mount(
        "/static",
        StaticFiles(directory=str(dossier_static)),
        name="static",
    )
    application.include_router(institution_router.router)

    def session_test():
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_session] = session_test

    # L'authentification est remplacée à sa frontière uniquement : les routes,
    # les dépendances CSRF, les requêtes SQL et les réponses HTTP restent réelles.
    monkeypatch.setattr(
        institution_router,
        "utilisateur_courant",
        lambda _request, session: session.get(
            Utilisateur, identite["utilisateur_id"]
        ) if identite["utilisateur_id"] else None,
    )

    @application.get("/__test/csrf")
    def jeton_csrf_test(request: Request):
        return {"token": obtenir_jeton_csrf(request)}

    try:
        with TestClient(application, follow_redirects=False) as client:
            yield {
                "client": client,
                "engine": engine,
                "institution_id": institution_id,
                "responsable_id": responsable_id,
                "etudiant_id": etudiant_id,
                "responsable_membre_id": responsable_membre_id,
            }
    finally:
        engine.dispose()


def test_parcours_http_affectation_tableau_de_bord_et_desactivation(
    espace_http_institutionnel,
):
    contexte = espace_http_institutionnel
    client = contexte["client"]
    institution_id = contexte["institution_id"]
    jeton = client.get("/__test/csrf").json()["token"]

    # Le responsable voit son établissement avant toute affectation.
    tableau_initial = client.get(
        f"/etablissement/tableau-de-bord?institution_id={institution_id}"
    )
    assert tableau_initial.status_code == 200
    assert "Université de test" in tableau_initial.text
    assert "Aucun cours institutionnel" in tableau_initial.text

    # Affectation via le formulaire réellement exposé par le tableau de bord.
    affectation = client.post(
        "/etablissement/membres/attribuer",
        data={
            "_csrf": jeton,
            "institution_id": str(institution_id),
            "identifiant": "ETU-HTTP-001",
            "role": "etudiant",
        },
    )
    assert affectation.status_code == 303
    assert "ok=membre_attribue" in affectation.headers["location"]

    with Session(contexte["engine"]) as session:
        membre = session.exec(
            select(MembreEtablissement).where(
                MembreEtablissement.institution_id == institution_id,
                MembreEtablissement.utilisateur_id == contexte["etudiant_id"],
            )
        ).first()
        assert membre is not None
        assert membre.est_actif is True
        assert membre.role == "etudiant"
        membre_id = membre.id

    tableau_apres_affectation = client.get(
        f"/etablissement/tableau-de-bord?institution_id={institution_id}"
    )
    assert tableau_apres_affectation.status_code == 200
    assert "Étudiant cible" in tableau_apres_affectation.text
    assert "ETU-HTTP-001" in tableau_apres_affectation.text
    assert "1</strong><span>étudiants actifs</span>" in tableau_apres_affectation.text

    # La désactivation est exécutée par HTTP avec le jeton CSRF et persiste.
    desactivation = client.post(
        f"/etablissement/membres/{membre_id}/desactiver",
        data={
            "_csrf": jeton,
            "institution_id": str(institution_id),
        },
    )
    assert desactivation.status_code == 303
    assert "ok=membre_desactive" in desactivation.headers["location"]

    with Session(contexte["engine"]) as session:
        membre_desactive = session.get(MembreEtablissement, membre_id)
        assert membre_desactive is not None
        assert membre_desactive.est_actif is False

    tableau_apres_desactivation = client.get(
        f"/etablissement/tableau-de-bord?institution_id={institution_id}"
    )
    assert tableau_apres_desactivation.status_code == 200
    assert "Étudiant cible" not in tableau_apres_desactivation.text
    assert "0</strong><span>étudiants actifs</span>" in tableau_apres_desactivation.text


def test_un_responsable_ne_peut_pas_affecter_ou_desactiver_hors_tenant(
    espace_http_institutionnel,
):
    contexte = espace_http_institutionnel
    client = contexte["client"]
    jeton = client.get("/__test/csrf").json()["token"]

    with Session(contexte["engine"]) as session:
        autre_institution = EtablissementPartenaire(
            nom="Autre établissement",
            code="AUTRE-HTTP",
        )
        session.add(autre_institution)
        session.commit()
        session.refresh(autre_institution)
        autre_institution_id = autre_institution.id

    affectation_hors_tenant = client.post(
        "/etablissement/membres/attribuer",
        data={
            "_csrf": jeton,
            "institution_id": str(autre_institution_id),
            "identifiant": "ETU-HTTP-001",
            "role": "etudiant",
        },
    )
    assert affectation_hors_tenant.status_code == 303
    assert affectation_hors_tenant.headers["location"] == "/classe"

    desactivation_responsable = client.post(
        f"/etablissement/membres/{contexte['responsable_membre_id']}/desactiver",
        data={
            "_csrf": jeton,
            "institution_id": str(contexte["institution_id"]),
        },
    )
    assert desactivation_responsable.status_code == 303
    assert "erreur=desactivation_invalide" in desactivation_responsable.headers["location"]

    with Session(contexte["engine"]) as session:
        responsable = session.get(
            MembreEtablissement, contexte["responsable_membre_id"]
        )
        assert responsable is not None
        assert responsable.est_actif is True
        assert session.exec(
            select(MembreEtablissement).where(
                MembreEtablissement.institution_id == autre_institution_id,
                MembreEtablissement.utilisateur_id == contexte["etudiant_id"],
            )
        ).first() is None
