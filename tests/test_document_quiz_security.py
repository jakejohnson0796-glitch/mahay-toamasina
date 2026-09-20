from types import SimpleNamespace

from app.models import StatutDocument
from app.routers import documents_router


def test_unapproved_document_cannot_generate_ai_quiz(monkeypatch):
    utilisateur = SimpleNamespace(id=1)
    document = SimpleNamespace(statut=StatutDocument.EN_ATTENTE, chemin_fichier="/tmp/must-not-open")

    class FakeSession:
        def get(self, model, identifier):
            return document

    monkeypatch.setattr(documents_router, "utilisateur_courant", lambda request, session: utilisateur)
    monkeypatch.setattr(documents_router, "acces_premium_ou_redirection", lambda utilisateur, session: None)

    response = documents_router.quiz_document(SimpleNamespace(session={}), 42, FakeSession())
    assert response.status_code == 303
    assert response.headers["location"] == "/documents"
