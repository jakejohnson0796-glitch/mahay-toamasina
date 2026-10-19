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
