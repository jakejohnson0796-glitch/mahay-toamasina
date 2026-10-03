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


def test_quiz_depuis_document_cree_une_tentative_interactive(monkeypatch):
    from app.routers import documents_router
    from app.models import StatutDocument, Filiere, Utilisateur

    utilisateur = SimpleNamespace(id=7, niveau="L1")
    document = SimpleNamespace(
        id=42,
        statut=StatutDocument.APPROUVE,
        chemin_fichier="/tmp/cours.pdf",
        matiere="Algèbre",
        titre="Cours Algèbre",
    )

    class FakeSession:
        def __init__(self):
            self.ajouts = []
            self.tentative = None
        def get(self, model, identifier):
            return document if model is not Utilisateur else utilisateur
        def add(self, obj):
            self.ajouts.append(obj)
            if obj.__class__.__name__ == "TentativeQuiz":
                obj.id = 123
                self.tentative = obj
        def commit(self):
            pass
        def refresh(self, obj):
            pass

    monkeypatch.setattr(documents_router, "utilisateur_courant", lambda request, session: utilisateur)
    monkeypatch.setattr(documents_router, "acces_premium_ou_redirection", lambda utilisateur, session: None)
    monkeypatch.setattr(documents_router, "ouvrir_fichier_local", lambda chemin: _FakeContext("/tmp/cours.pdf"))
    monkeypatch.setattr(documents_router, "extraire_texte", lambda chemin: "Texte de cours suffisamment long pour générer un quiz.")
    monkeypatch.setattr(
        documents_router,
        "generer_quiz_depuis_texte",
        lambda texte, nb_questions=5: [
            {
                "question": f"Question {i}",
                "choix": ["A", "B", "C", "D"],
                "index_bonne_reponse": 0,
                "explication": "Explication",
                "notion": "Algèbre",
            }
            for i in range(nb_questions)
        ],
    )
    monkeypatch.setattr(documents_router.ai_queue, "planifier_verification_quiz", lambda tentative_id: 9)

    session = FakeSession()
    response = documents_router.quiz_document(SimpleNamespace(session={}), 42, session)
    assert response.status_code == 303
    assert response.headers["location"] == "/quiz/123"
    assert session.tentative is not None
    assert session.tentative.nb_questions == 5
    assert session.tentative.reponses_json is None


class _FakeContext:
    def __init__(self, chemin):
        self.chemin = chemin
    def __enter__(self):
        return self.chemin
    def __exit__(self, exc_type, exc, tb):
        return False


def test_quiz_document_cree_une_tentative_interactive():
    from app.routers import documents_router
    code = documents_router.quiz_document.__code__
    assert "TentativeQuiz" in code.co_names


def test_correction_question_sur_la_meme_page():
    from pathlib import Path
    contenu = Path(__file__).resolve().parents[1].joinpath("app","templates","quiz_passer.html").read_text(encoding="utf-8")
    assert "correction_visible" in contenu
    assert "Bonne réponse" in contenu
    assert "Explication" in contenu


def test_soumission_reste_sur_la_page_quiz():
    from pathlib import Path
    contenu = Path(__file__).resolve().parents[1].joinpath("app","routers","quiz_router.py").read_text(encoding="utf-8")
    assert 'return RedirectResponse(f"/quiz/{tentative.id}", status_code=303)' in contenu
