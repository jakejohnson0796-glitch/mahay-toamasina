"""Route-level regression tests for private, per-student course revision sheets.

These tests exercise the HTTP route guards and prove that both the rendered
revision page and its file exports are built for the currently authenticated
student. The shared source fiche must not be treated as the personalized output.
"""
from datetime import datetime
import json
from types import SimpleNamespace

import pytest

from app import course_revision
from app.models import (
    Document,
    Filiere,
    StatutDocument,
    StatutFicheRevisionDocument,
    TypeDocument,
)
from app.routers import documents_router


class FakeResult:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class FakeSession:
    def __init__(self, document, fiche=None):
        self.document = document
        self.fiche = fiche
        self.queries = 0

    def get(self, model, _identifier):
        if model is Document:
            return self.document
        if model is Filiere:
            return None
        return None

    def exec(self, _query):
        self.queries += 1
        return FakeResult(self.fiche)


class NoQuerySession(FakeSession):
    def exec(self, _query):
        raise AssertionError("La fiche ne doit pas être chargée avant le contrôle d'accès.")


def make_document(*, statut=StatutDocument.APPROUVE, type_document=TypeDocument.COURS, cercle_id=None):
    return SimpleNamespace(
        id=51,
        reference="TEST-REVISION-51",
        titre="Matrices et déterminants",
        matiere="Mathématiques",
        statut=statut,
        type_document=type_document,
        cercle_id=cercle_id,
        filiere_id=None,
        portee_academique="universitaire",
        niveau_scolaire_id=None,
        option_scolaire_id=None,
    )


def make_fiche():
    return SimpleNamespace(
        document_id=51,
        statut=StatutFicheRevisionDocument.TERMINEE,
        version_generation=course_revision.VERSION_GENERATION_DOCUMENT,
        contenu_json=json.dumps({"resume": "Contenu source partagé"}),
        sources_json="{}",
        date_creation=datetime(2026, 10, 25, 8, 0),
        date_generation=datetime(2026, 10, 25, 8, 5),
    )


def make_user(user_id, name):
    return SimpleNamespace(id=user_id, nom=name, role="ETUDIANT")


@pytest.mark.parametrize("route_kind", ["consultation", "telechargement"])
def test_fiche_revision_refuse_les_visiteurs_anonymes(monkeypatch, route_kind):
    monkeypatch.setattr(documents_router, "utilisateur_courant", lambda _request, _session: None)

    class NoReadSession:
        def get(self, *_args):
            raise AssertionError("Un visiteur anonyme ne doit pas lire le document.")

        def exec(self, *_args):
            raise AssertionError("Un visiteur anonyme ne doit pas lire la fiche.")

    request = SimpleNamespace(session={})
    session = NoReadSession()
    if route_kind == "consultation":
        response = documents_router.consulter_fiche_revision_document(request, 51, session)
    else:
        response = documents_router.telecharger_fiche_revision_document(request, 51, "pdf", session)

    assert response.status_code == 303
    assert response.headers["location"] == "/connexion"


@pytest.mark.parametrize(
    ("statut", "type_document"),
    [
        (StatutDocument.EN_ATTENTE, TypeDocument.COURS),
        (StatutDocument.REJETE, TypeDocument.COURS),
        (StatutDocument.APPROUVE, TypeDocument.ANNALE),
    ],
)
@pytest.mark.parametrize("route_kind", ["consultation", "telechargement"])
def test_fiche_revision_refuse_les_ressources_non_eligibles(
    monkeypatch, statut, type_document, route_kind
):
    utilisateur = make_user(7, "Étudiant")
    document = make_document(statut=statut, type_document=type_document)
    session = NoQuerySession(document, make_fiche())
    monkeypatch.setattr(
        documents_router,
        "utilisateur_courant",
        lambda _request, _session: utilisateur,
    )

    request = SimpleNamespace(session={})
    if route_kind == "consultation":
        response = documents_router.consulter_fiche_revision_document(request, 51, session)
    else:
        response = documents_router.telecharger_fiche_revision_document(request, 51, "pdf", session)

    assert response.status_code == 303
    assert response.headers["location"] == "/documents"


@pytest.mark.parametrize("route_kind", ["consultation", "telechargement"])
def test_fiche_revision_refuse_un_non_membre_du_cercle(monkeypatch, route_kind):
    utilisateur = make_user(7, "Étudiant")
    document = make_document(cercle_id=321)
    session = NoQuerySession(document, make_fiche())
    monkeypatch.setattr(
        documents_router,
        "utilisateur_courant",
        lambda _request, _session: utilisateur,
    )
    monkeypatch.setattr(documents_router, "_est_membre_cercle", lambda *_args: False)

    request = SimpleNamespace(session={})
    if route_kind == "consultation":
        response = documents_router.consulter_fiche_revision_document(request, 51, session)
    else:
        response = documents_router.telecharger_fiche_revision_document(request, 51, "pdf", session)

    assert response.status_code == 303
    assert response.headers["location"] == "/cercles/321"


def test_consultation_construit_une_fiche_personnalisee_pour_le_compte_connecte(monkeypatch):
    users = [make_user(7, "Étudiant A"), make_user(8, "Étudiant B")]
    current = {"user": users[0]}
    source = {"resume": "Contenu source partagé"}
    contextes = []
    profils_generes = []

    monkeypatch.setattr(
        documents_router,
        "utilisateur_courant",
        lambda _request, _session: current["user"],
    )
    monkeypatch.setattr(course_revision, "normaliser_fiche_revision", lambda _raw: dict(source))

    def personnaliser(_session, _document, utilisateur_id, fiche):
        profil = {"utilisateur_id": utilisateur_id}
        profils_generes.append(profil)
        return {**fiche, "profil_personnalise": profil}

    monkeypatch.setattr(
        course_revision,
        "personnaliser_fiche_revision_document",
        personnaliser,
    )
    monkeypatch.setattr(
        documents_router,
        "templates",
        SimpleNamespace(
            TemplateResponse=lambda _request, _template, contexte: (
                contextes.append(contexte) or SimpleNamespace(status_code=200)
            )
        ),
    )

    for user in users:
        current["user"] = user
        response = documents_router.consulter_fiche_revision_document(
            SimpleNamespace(session={}),
            51,
            FakeSession(make_document(), make_fiche()),
        )
        assert response.status_code == 200

    assert [c["fiche_contenu"]["profil_personnalise"]["utilisateur_id"] for c in contextes] == [7, 8]
    assert [p["utilisateur_id"] for p in profils_generes] == [7, 8]
    assert source == {"resume": "Contenu source partagé"}


@pytest.mark.parametrize(
    ("format_fichier", "media_type", "prefix"),
    [
        ("pdf", "application/pdf", "pdf"),
        (
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx",
        ),
    ],
)
def test_export_revision_recalcule_le_profil_du_compte_et_ne_cache_pas_la_fiche(
    monkeypatch, format_fichier, media_type, prefix
):
    users = [make_user(7, "Étudiant A"), make_user(8, "Étudiant B")]
    current = {"user": users[0]}
    profils_generes = []

    monkeypatch.setattr(
        documents_router,
        "utilisateur_courant",
        lambda _request, _session: current["user"],
    )
    monkeypatch.setattr(
        course_revision,
        "normaliser_fiche_revision",
        lambda _raw: {"resume": "Contenu source partagé"},
    )

    def personnaliser(_session, _document, utilisateur_id, fiche):
        profil = {"utilisateur_id": utilisateur_id}
        profils_generes.append(profil)
        return {**fiche, "profil_personnalise": profil}

    monkeypatch.setattr(
        course_revision,
        "personnaliser_fiche_revision_document",
        personnaliser,
    )

    def fabriquer_export(fiche, _cours, _seance, nom):
        return f"{prefix}:{nom}:{fiche['profil_personnalise']['utilisateur_id']}".encode()

    monkeypatch.setattr(course_revision, "generer_pdf", fabriquer_export)
    monkeypatch.setattr(course_revision, "generer_docx", fabriquer_export)

    sorties = []
    for user in users:
        current["user"] = user
        response = documents_router.telecharger_fiche_revision_document(
            SimpleNamespace(session={}),
            51,
            format_fichier,
            FakeSession(make_document(), make_fiche()),
        )
        sorties.append(response)
        assert response.status_code == 200
        assert response.media_type == media_type
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["x-content-type-options"] == "nosniff"

    assert [r.body for r in sorties] == [
        f"{prefix}:Étudiant A:7".encode(),
        f"{prefix}:Étudiant B:8".encode(),
    ]
    assert [p["utilisateur_id"] for p in profils_generes] == [7, 8]
