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
    return Utilisateur(
        nom="Test Utilisateur",
        telephone="0341234567",
        mot_de_passe_hash="hash",
        derniere_activite_le=derniere_activite_le,
    )


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
