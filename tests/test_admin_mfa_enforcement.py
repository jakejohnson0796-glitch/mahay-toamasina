from types import SimpleNamespace

from app.force_password_change import chemin_autorise_pendant_configuration_mfa_admin
from app.models import RoleUtilisateur
from app.routers import auth_router
from app.main import _configuration_documentation


def test_un_admin_sans_totp_est_redirige_vers_le_parcours_mfa():
    admin = SimpleNamespace(
        role=RoleUtilisateur.ADMIN,
        totp_active=False,
        doit_changer_mot_de_passe=False,
    )

    response = auth_router._redirection_apres_connexion(admin)

    assert response.status_code == 303
    assert response.headers["location"] == "/securite?admin_mfa_obligatoire=1"


def test_un_admin_avec_totp_peut_reprendre_le_parcours_normal():
    admin = SimpleNamespace(
        role=RoleUtilisateur.ADMIN,
        totp_active=True,
        doit_changer_mot_de_passe=False,
    )

    response = auth_router._redirection_apres_connexion(admin)

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_un_admin_ne_peut_pas_desactiver_son_facteur(monkeypatch):
    admin = SimpleNamespace(role=RoleUtilisateur.ADMIN, totp_active=True)
    monkeypatch.setattr(auth_router, "utilisateur_courant", lambda *_args: admin)

    response = auth_router.desactiver_2fa(
        SimpleNamespace(),
        mot_de_passe="mot-de-passe-de-test",
        session=SimpleNamespace(),
        _csrf=None,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/securite?erreur=totp_admin_obligatoire"


def test_seul_le_parcours_mfa_reste_ouvert_aux_admins_sans_totp():
    assert chemin_autorise_pendant_configuration_mfa_admin("GET", "/securite")
    assert chemin_autorise_pendant_configuration_mfa_admin("POST", "/securite/2fa/demarrer")
    assert chemin_autorise_pendant_configuration_mfa_admin("GET", "/securite/2fa/configurer")
    assert chemin_autorise_pendant_configuration_mfa_admin("POST", "/securite/2fa/confirmer")
    assert chemin_autorise_pendant_configuration_mfa_admin("POST", "/deconnexion")
    assert chemin_autorise_pendant_configuration_mfa_admin("GET", "/static/app.css")
    assert not chemin_autorise_pendant_configuration_mfa_admin("GET", "/admin")
    assert not chemin_autorise_pendant_configuration_mfa_admin("GET", "/admin/utilisateurs")
    assert not chemin_autorise_pendant_configuration_mfa_admin("GET", "/cercles/12")
    assert not chemin_autorise_pendant_configuration_mfa_admin("POST", "/admin/utilisateurs/12/valider")


def test_les_deux_websockets_refusent_un_admin_sans_totp():
    racine = Path(__file__).resolve().parents[1]
    cercles = (racine / "app" / "routers" / "cercles_router.py").read_text(encoding="utf-8")
    tableau = (racine / "app" / "routers" / "classe_router.py").read_text(encoding="utf-8")

    garde = "utilisateur.role == RoleUtilisateur.ADMIN and not utilisateur.totp_active"
    assert garde in cercles
    assert garde in tableau


def test_documentation_api_est_desactivee_en_production():
    configuration = _configuration_documentation("production")

    assert configuration == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }


def test_documentation_api_reste_disponible_en_developpement():
    configuration = _configuration_documentation("developpement")

    assert configuration == {
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }


def test_template_signale_le_totp_obligatoire_et_cache_la_desactivation_admin():
    from pathlib import Path

    template = (
        Path(__file__).resolve().parents[1] / "app" / "templates" / "securite.html"
    ).read_text(encoding="utf-8")

    assert "Configuration obligatoire pour l'administrateur." in template
    assert 'utilisateur.role.value == "admin"' in template
