import os
import re
import tempfile
from types import SimpleNamespace

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(suffix='.db', delete=False).name}"
os.environ.setdefault("SESSION_SECRET_KEY", "cle-de-test-uniquement-jamais-en-production")

from starlette.testclient import TestClient

from app.main import app
from app.models import StatutDocument
from app.routers import documents_router
from app.storage import stockage_distant_actif


def test_csp_reelle_sur_reponse_http():
    client = TestClient(app)
    response = client.get("/connexion")

    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    # MODIF : unsafe-inline est toléré uniquement dans style-src-attr pour KaTeX.
    assert "script-src-attr 'none'" in csp
    assert "style-src-attr 'unsafe-inline' 'unsafe-hashes'" in csp
    assert "strict-dynamic" in csp
    assert "https://cdn.jsdelivr.net" in csp
    assert "strict-dynamic" in csp

    match = re.search(r"script-src[^;]*'nonce-([^']+)'", csp)
    assert match, csp
    nonce = match.group(1)
    assert f'nonce="{nonce}"' in response.text


def test_telechargement_document_general_utilise_un_compte_courant(monkeypatch):
    contenu = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    contenu.write(b"%PDF-1.4 test")
    contenu.close()

    document = SimpleNamespace(
        statut=StatutDocument.APPROUVE,
        cercle_id=None,
        nb_telechargements=0,
        chemin_fichier=contenu.name,
        id=42,
    )
    utilisateur = SimpleNamespace(id=17)

    class FakeSession:
        def get(self, model, identifier):
            return document

        def add(self, objet):
            pass

        def commit(self):
            pass

    monkeypatch.setattr(documents_router, "utilisateur_courant", lambda request, session: utilisateur)
    monkeypatch.setattr(documents_router, "limite_depassee", lambda *args, **kwargs: False)
    monkeypatch.setattr(documents_router, "stockage_distant_actif", lambda: False)
    monkeypatch.setattr(
        documents_router,
        "Path",
        documents_router.Path,
    )

    response = documents_router.telecharger_document(
        SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")),
        42,
        FakeSession(),
    )

    assert response.status_code == 200
    assert document.nb_telechargements == 1


def test_document_de_cercle_ne_peut_pas_etre_telecharge_par_un_non_membre(monkeypatch):
    document = SimpleNamespace(
        statut=StatutDocument.APPROUVE,
        cercle_id=99,
        nb_telechargements=0,
        chemin_fichier="/tmp/document-prive.pdf",
    )
    utilisateur = SimpleNamespace(id=17)

    class FakeSession:
        def get(self, model, identifier):
            return document

    monkeypatch.setattr(documents_router, "utilisateur_courant", lambda request, session: utilisateur)
    monkeypatch.setattr(documents_router, "_est_membre_cercle", lambda session, cercle_id, utilisateur_id: False)

    response = documents_router.telecharger_document(
        SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")),
        42,
        FakeSession(),
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/cercles/99"
    assert document.nb_telechargements == 0
