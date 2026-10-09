from datetime import datetime, timedelta
from types import SimpleNamespace

from app.auth import (
    creer_rappel_inactivite_si_necessaire,
    jours_inactivite,
)
from app.models import Notification, TypeNotification, Utilisateur


class FakeSession:
    def __init__(self):
        self.objects = []
        self.next_id = 1

    def add(self, obj):
        if isinstance(obj, Notification) and obj.id is None:
            obj.id = self.next_id
            self.next_id += 1
        self.objects.append(obj)

    def flush(self):
        for obj in self.objects:
            if isinstance(obj, Notification) and obj.id is None:
                obj.id = self.next_id
                self.next_id += 1

    def commit(self):
        return None

    def refresh(self, obj):
        return None


def creer_utilisateur(derniere_activite_le):
    utilisateur = Utilisateur(
        nom="Test Utilisateur",
        telephone="0341234567",
        mot_de_passe_hash="hash",
        derniere_activite_le=derniere_activite_le,
    )
    utilisateur.id = 42
    return utilisateur


def test_compteur_inactivite_en_jours_complets():
    maintenant = datetime(2026, 9, 27, 12, 0, 0)
    utilisateur = creer_utilisateur(maintenant - timedelta(days=3, hours=2))
    assert jours_inactivite(utilisateur, maintenant) == 3


def test_aucun_rappel_avant_trois_jours():
    maintenant = datetime(2026, 9, 27, 12, 0, 0)
    utilisateur = creer_utilisateur(maintenant - timedelta(days=2, hours=23, minutes=59))
    session = FakeSession()

    jours, notification_id = creer_rappel_inactivite_si_necessaire(
        utilisateur, session, maintenant=maintenant
    )

    assert jours == 2
    assert notification_id is None
    assert not [obj for obj in session.objects if isinstance(obj, Notification)]


def test_notification_a_la_prochaine_connexion_apres_trois_jours():
    maintenant = datetime(2026, 9, 27, 12, 0, 0)
    utilisateur = creer_utilisateur(maintenant - timedelta(days=3))
    session = FakeSession()

    jours, notification_id = creer_rappel_inactivite_si_necessaire(
        utilisateur, session, maintenant=maintenant
    )

    notifications = [obj for obj in session.objects if isinstance(obj, Notification)]
    assert jours == 3
    assert notification_id == notifications[0].id
    assert notifications[0].type_notification == TypeNotification.INACTIVITE_3_JOURS
    assert notifications[0].destinataire_id == utilisateur.id
    assert utilisateur.derniere_activite_le == maintenant



class FakeNotificationRouteSession:
    def __init__(self, notification):
        self.notification = notification
        self.added = []
        self.commits = 0

    def get(self, model, identifier):
        if self.notification and self.notification.id == identifier:
            return self.notification
        return None

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1


def test_ouvrir_notification_marque_comme_lue_et_ouvre_le_dashboard(monkeypatch):
    from app.routers import notifications_router

    utilisateur = SimpleNamespace(id=42)
    monkeypatch.setattr(
        notifications_router,
        "utilisateur_courant",
        lambda request, session: utilisateur,
    )
    notification = SimpleNamespace(
        id=99,
        destinataire_id=42,
        cercle_id=None,
        type_notification=TypeNotification.INACTIVITE_3_JOURS,
        lu=False,
    )
    session = FakeNotificationRouteSession(notification)
    request = SimpleNamespace(session={"notification_inactivite": {"notification_id": 99}})

    response = notifications_router.ouvrir_notification(99, request, session, None)

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert notification.lu is True
    assert session.commits == 1
    assert "notification_inactivite" not in request.session


def test_ouvrir_notification_refuse_de_modifier_celle_d_un_autre_utilisateur(monkeypatch):
    from app.routers import notifications_router

    monkeypatch.setattr(
        notifications_router,
        "utilisateur_courant",
        lambda request, session: SimpleNamespace(id=7),
    )
    notification = SimpleNamespace(
        id=99,
        destinataire_id=42,
        cercle_id=None,
        type_notification=TypeNotification.INACTIVITE_3_JOURS,
        lu=False,
    )
    session = FakeNotificationRouteSession(notification)
    request = SimpleNamespace(session={})

    response = notifications_router.ouvrir_notification(99, request, session, None)

    assert response.status_code == 303
    assert response.headers["location"] == "/notifications"
    assert notification.lu is False
    assert session.commits == 0


def test_l_action_ouvrir_est_un_post_protege_par_csrf():
    from pathlib import Path

    racine = Path(__file__).resolve().parents[1]
    route = (racine / "app" / "routers" / "notifications_router.py").read_text(encoding="utf-8")
    template = (racine / "app" / "templates" / "notifications.html").read_text(encoding="utf-8")

    assert '@router.post("/notifications/{notification_id}/ouvrir")' in route
    assert '_csrf: None = Depends(verifier_csrf)' in route
    assert 'action="/notifications/{{ n.id }}/ouvrir"' in template
    assert '<input type="hidden" name="_csrf" value="{{ jeton_csrf(request) }}">' in template
