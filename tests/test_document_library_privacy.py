from types import SimpleNamespace

from sqlalchemy.dialects import sqlite

from app.routers import documents_router


class _Rows:
    def all(self):
        return []


class _Session:
    def __init__(self):
        self.sql = []

    def exec(self, statement):
        self.sql.append(str(statement.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})))
        return _Rows()


def test_bibliotheque_generale_filtre_les_documents_prives_aux_membres_du_cercle(monkeypatch):
    utilisateur = SimpleNamespace(id=17)
    session = _Session()
    monkeypatch.setattr(documents_router, "utilisateur_courant", lambda _request, _session: utilisateur)
    monkeypatch.setattr(
        documents_router.templates,
        "TemplateResponse",
        lambda *_args, **_kwargs: SimpleNamespace(rendered=True),
    )

    response = documents_router.liste_documents(SimpleNamespace(query_params={}), session=session)

    assert response.rendered
    requete_documents = next(sql for sql in session.sql if "FROM document" in sql and "statut" in sql)
    assert "document.cercle_id IS NULL" in requete_documents
    assert "document.cercle_id IN" in requete_documents
    assert any("from membrecercle" in sql.lower() for sql in session.sql)


def test_bibliotheque_anonyme_ne_liste_jamais_les_documents_de_cercle(monkeypatch):
    session = _Session()
    monkeypatch.setattr(documents_router, "utilisateur_courant", lambda _request, _session: None)
    monkeypatch.setattr(
        documents_router.templates,
        "TemplateResponse",
        lambda *_args, **_kwargs: SimpleNamespace(rendered=True),
    )

    response = documents_router.liste_documents(SimpleNamespace(query_params={}), session=session)

    assert response.rendered
    requete_documents = next(sql for sql in session.sql if "FROM document" in sql and "statut" in sql)
    assert "document.cercle_id IS NULL" in requete_documents
    assert "document.cercle_id IN" not in requete_documents



def test_telechargement_document_refuse_un_visiteur_non_connecte(monkeypatch):
    class FakeSession:
        def get(self, *_args, **_kwargs):
            raise AssertionError("Un visiteur anonyme ne doit même pas charger le document.")

    monkeypatch.setattr(documents_router, "utilisateur_courant", lambda _request, _session: None)
    response = documents_router.telecharger_document(
        SimpleNamespace(client=SimpleNamespace(host="203.0.113.10")),
        document_id=123,
        session=FakeSession(),
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/connexion"


def test_telechargement_document_reste_possible_pour_un_compte_connecte(monkeypatch):
    from app.models import StatutDocument

    utilisateur = SimpleNamespace(id=17, nom="Etudiant de test")
    document = SimpleNamespace(
        id=123,
        statut=StatutDocument.APPROUVE,
        cercle_id=None,
        nb_telechargements=0,
        chemin_fichier="cours-test.pdf",
    )

    class FakeSession:
        def __init__(self):
            self.ajouts = []
            self.commits = 0

        def get(self, *_args, **_kwargs):
            return document

        def add(self, obj):
            self.ajouts.append(obj)

        def commit(self):
            self.commits += 1

    session = FakeSession()
    monkeypatch.setattr(documents_router, "utilisateur_courant", lambda _request, _session: utilisateur)
    monkeypatch.setattr(documents_router, "limite_depassee", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(documents_router, "stockage_distant_actif", lambda: True)
    monkeypatch.setattr(
        documents_router,
        "obtenir_url_telechargement",
        lambda *_args, **_kwargs: "https://storage.example/document-signe",
    )

    response = documents_router.telecharger_document(
        SimpleNamespace(client=SimpleNamespace(host="203.0.113.10")),
        document_id=123,
        session=session,
    )

    assert response.status_code == 307
    assert response.headers["location"] == "https://storage.example/document-signe"
    assert document.nb_telechargements == 1
    assert session.commits == 2


def test_interface_ne_donne_pas_de_lien_de_telechargement_aux_visiteurs():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "templates"
        / "documents_list.html"
    ).read_text(encoding="utf-8")
    actions = source.split('<div class="doc-actions">', 1)[1].split("</div>", 1)[0]

    assert actions.index("{% if utilisateur %}") < actions.index(
        'href="/documents/{{ doc.id }}/telecharger"'
    )
    assert "{% else %}" in actions
    assert 'href="/connexion">Connectez-vous pour télécharger</a>' in actions
