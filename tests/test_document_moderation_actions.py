from types import SimpleNamespace

from app.models import Document, RoleUtilisateur, StatutDocument
from app.routers import documents_router


class _ExecResult:
    def all(self):
        return []


class FakeSession:
    def __init__(self, document):
        self.document = document
        self.added = []
        self.deleted = []
        self.commits = 0

    def get(self, model, identifier):
        return self.document

    def add(self, item):
        self.added.append(item)

    def delete(self, item):
        self.deleted.append(item)

    def commit(self):
        self.commits += 1

    def exec(self, query):
        return _ExecResult()


def _admin(monkeypatch):
    utilisateur = SimpleNamespace(role=RoleUtilisateur.ADMIN, id=1)
    monkeypatch.setattr(documents_router, "utilisateur_courant", lambda request, session: utilisateur)
    return utilisateur


def test_approuver_document_change_le_statut_et_redirige(monkeypatch):
    _admin(monkeypatch)
    document = SimpleNamespace(statut=StatutDocument.EN_ATTENTE)
    session = FakeSession(document)

    response = documents_router.approuver_document(
        SimpleNamespace(), 42, session, None
    )

    assert document.statut == StatutDocument.APPROUVE
    assert session.commits == 1
    assert response.status_code == 303
    assert response.headers["location"] == "/moderation?resultat=approuve"


def test_rejeter_document_change_le_statut_et_redirige(monkeypatch):
    _admin(monkeypatch)
    document = SimpleNamespace(statut=StatutDocument.EN_ATTENTE)
    session = FakeSession(document)

    response = documents_router.rejeter_document(
        SimpleNamespace(), 42, session, None
    )

    assert document.statut == StatutDocument.REJETE
    assert session.commits == 1
    assert response.headers["location"] == "/moderation?resultat=rejete"


def test_supprimer_document_supprime_le_fichier_et_la_ligne(monkeypatch):
    _admin(monkeypatch)
    document = SimpleNamespace(
        statut=StatutDocument.REJETE,
        chemin_fichier="documents/test.pdf",
    )
    session = FakeSession(document)
    supprime = []
    monkeypatch.setattr(
        documents_router,
        "supprimer_fichier",
        lambda chemin: supprime.append(chemin),
    )

    response = documents_router.supprimer_document(
        SimpleNamespace(), 42, session, None
    )

    assert supprime == ["documents/test.pdf"]
    assert session.deleted == [document]
    assert session.commits == 2
    assert response.headers["location"] == "/moderation?resultat=supprime"


def test_actions_admin_refusent_un_utilisateur_non_admin(monkeypatch):
    utilisateur = SimpleNamespace(role=RoleUtilisateur.ETUDIANT, id=7)
    monkeypatch.setattr(documents_router, "utilisateur_courant", lambda request, session: utilisateur)
    document = SimpleNamespace(statut=StatutDocument.EN_ATTENTE)
    session = FakeSession(document)

    response = documents_router.approuver_document(
        SimpleNamespace(), 42, session, None
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert document.statut == StatutDocument.EN_ATTENTE


def test_moderation_template_expose_les_trois_actions():
    from pathlib import Path

    template = Path(__file__).resolve().parents[1] / "app" / "templates" / "moderation.html"
    contenu = template.read_text(encoding="utf-8")

    assert 'action="/moderation/{{ doc.id }}/approuver"' in contenu
    assert 'action="/moderation/{{ doc.id }}/rejeter"' in contenu
    assert 'action="/moderation/{{ doc.id }}/supprimer"' in contenu
    assert "documents_rejetes" in contenu
