from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from app.auth import notifier_nouvelle_inscription_aux_admins
from app.models import Notification, RoleUtilisateur, TypeNotification
from app.templating import _jours_depuis_creation


ROOT = Path(__file__).resolve().parents[1]


class _ResultatFaux:
    def __init__(self, lignes):
        self.lignes = lignes

    def all(self):
        return self.lignes


class _SessionFausse:
    def __init__(self, administrateurs):
        self.administrateurs = administrateurs
        self.ajouts = []

    def exec(self, _requete):
        return _ResultatFaux(self.administrateurs)

    def add(self, objet):
        self.ajouts.append(objet)


def test_nouvelle_inscription_notifie_tous_les_admins():
    admins = [
        SimpleNamespace(id=1, role=RoleUtilisateur.ADMIN),
        SimpleNamespace(id=2, role=RoleUtilisateur.ADMIN),
    ]
    utilisateur = SimpleNamespace(
        id=42,
        nom="Rakoto Jean",
        date_creation=datetime(2026, 9, 28, 7, 0, 0),
    )
    session = _SessionFausse(admins)

    total = notifier_nouvelle_inscription_aux_admins(utilisateur, session)

    assert total == 2
    assert len(session.ajouts) == 2
    assert all(isinstance(n, Notification) for n in session.ajouts)
    assert {n.destinataire_id for n in session.ajouts} == {1, 2}
    assert all(n.acteur_id == 42 for n in session.ajouts)
    assert all(n.type_notification == TypeNotification.NOUVELLE_INSCRIPTION for n in session.ajouts)


def test_anciennete_compte_est_calculee_en_jours_complets():
    maintenant = datetime(2026, 9, 28, 12, 0, 0)
    utilisateur = SimpleNamespace(
        date_creation=maintenant - timedelta(days=7, hours=2),
    )
    assert _jours_depuis_creation(utilisateur, maintenant) == 7


def test_interface_admin_expose_notification_et_anciennete():
    admin = (ROOT / "app" / "templates" / "admin_index.html").read_text(encoding="utf-8")
    users = (ROOT / "app" / "templates" / "admin_utilisateurs.html").read_text(encoding="utf-8")
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")

    assert 'id="nouveaux-arrivants"' in admin
    assert "nb_nouveaux_arrivants" in admin
    assert "jours_depuis_creation" in admin
    assert "Ancienneté" in users
    assert "date_creation.strftime" in users
    assert "nb_notifications_admin_nouvelles(request)" in base
