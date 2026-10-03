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
    document = SimpleNamespace(
        statut=StatutDocument.EN_ATTENTE,
        titre="Algèbre",
        reference="MG-INF-2026-TEST",
    )
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
    document = SimpleNamespace(
        statut=StatutDocument.EN_ATTENTE,
        titre="Algèbre",
        reference="MG-INF-2026-TEST",
    )
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
        titre="Algèbre",
        reference="MG-INF-2026-TEST",
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


def test_actions_de_moderation_creent_une_notification_dapprobation(monkeypatch):
    admin = SimpleNamespace(role=RoleUtilisateur.ADMIN, id=1)
    monkeypatch.setattr(documents_router, "utilisateur_courant", lambda request, session: admin)
    document = SimpleNamespace(
        statut=StatutDocument.EN_ATTENTE,
        uploader_id=42,
        titre="Algèbre",
        reference="MG-INF-2026-TEST",
        chemin_fichier="documents/test.pdf",
    )
    session = FakeSession(document)

    documents_router.approuver_document(SimpleNamespace(), 42, session, None)
    notifications = [
        item for item in session.added
        if getattr(item, "type_notification", None) == documents_router.TypeNotification.DOCUMENT_APPROUVE
    ]
    assert len(notifications) == 1
    assert notifications[0].destinataire_id == 42
    assert notifications[0].acteur_id == 1


def test_rejet_cree_une_notification_pour_le_deposant(monkeypatch):
    admin = SimpleNamespace(role=RoleUtilisateur.ADMIN, id=1)
    monkeypatch.setattr(documents_router, "utilisateur_courant", lambda request, session: admin)
    document = SimpleNamespace(
        statut=StatutDocument.EN_ATTENTE,
        uploader_id=42,
        titre="Algèbre",
        reference="MG-INF-2026-TEST",
        chemin_fichier="documents/test.pdf",
    )
    session = FakeSession(document)

    documents_router.rejeter_document(SimpleNamespace(), 42, session, None)
    notifications = [
        item for item in session.added
        if getattr(item, "type_notification", None) == documents_router.TypeNotification.DOCUMENT_REJETE
    ]
    assert len(notifications) == 1
    assert notifications[0].destinataire_id == 42


def test_moderation_expose_une_action_consulter():
    from pathlib import Path
    template = Path(__file__).resolve().parents[1] / "app" / "templates" / "moderation.html"
    contenu = template.read_text(encoding="utf-8")
    assert 'href="/moderation/{{ doc.id }}/consulter"' in contenu


def test_routes_de_consultation_sont_exposees():
    from app.routers.documents_router import consulter_document_moderation, fichier_document_moderation
    assert consulter_document_moderation.__annotations__["document_id"] is int
    assert fichier_document_moderation.__annotations__["document_id"] is int


def test_apercu_moderation_est_charge_en_blob_same_origin():
    from pathlib import Path
    template = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "templates"
        / "moderation_document_preview.html"
    ).read_text(encoding="utf-8")
    assert 'fetch(fileUrl' in template
    assert 'URL.createObjectURL(blob)' in template


def test_route_fichier_moderation_proxy_les_octets():
    from app.routers.documents_router import fichier_document_moderation
    code = fichier_document_moderation.__code__
    assert "Response" in code.co_names
    assert "ouvrir_fichier_local" in code.co_names
