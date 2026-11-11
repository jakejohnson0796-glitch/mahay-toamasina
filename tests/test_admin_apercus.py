from pathlib import Path
from types import SimpleNamespace

from fastapi.responses import RedirectResponse

from app.models import RoleUtilisateur
from app.routers import admin_router, dashboard_router


ROOT = Path(__file__).resolve().parents[1]


def _admin():
    return SimpleNamespace(
        id=7,
        nom="Administrateur de test",
        role=RoleUtilisateur.ADMIN,
        mot_de_passe_confirmation_admin_hash="hash",
    )


def _capture_template(monkeypatch):
    appels = {}

    def rendre(request, template, contexte):
        appels["request"] = request
        appels["template"] = template
        appels["contexte"] = contexte
        return appels

    monkeypatch.setattr(admin_router.templates, "TemplateResponse", rendre)
    return appels


def test_selecteur_apercu_reserve_a_l_administrateur(monkeypatch):
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: None)
    reponse = admin_router.page_admin_apercus(SimpleNamespace(), SimpleNamespace())

    assert isinstance(reponse, RedirectResponse)
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/"


def test_selecteur_apercu_est_accessible_a_l_admin(monkeypatch):
    appels = _capture_template(monkeypatch)
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: _admin())

    reponse = admin_router.page_admin_apercus(SimpleNamespace(), SimpleNamespace())

    assert reponse["template"] == "admin_apercus.html"
    assert reponse["contexte"]["utilisateur"].role == RoleUtilisateur.ADMIN


def test_apercus_utilisent_des_profils_fictifs_et_des_templates_distincts(monkeypatch):
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: _admin())
    appels = _capture_template(monkeypatch)

    cas = {
        "etudiant": ("dashboard_etudiant.html", RoleUtilisateur.ETUDIANT),
        "enseignant": ("dashboard_enseignant.html", RoleUtilisateur.PROFESSEUR),
        "repetiteur": ("dashboard_repetiteur.html", RoleUtilisateur.REPETITEUR),
    }
    for espace, (template, role) in cas.items():
        reponse = admin_router.page_admin_apercu_espace(
            espace,
            SimpleNamespace(),
            SimpleNamespace(),
        )
        contexte = reponse["contexte"]
        assert reponse["template"] == template
        assert contexte["utilisateur"].id == -1
        assert contexte["utilisateur"].role == role
        assert contexte["mode_apercu_admin"] is True
        assert contexte["mode_apercu_espace"] == espace
        assert "utilisateur" in contexte



def test_apercu_repetiteur_utilise_un_profil_fictif_valide_et_son_propre_template(monkeypatch):
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: _admin())
    _capture_template(monkeypatch)

    reponse = admin_router.page_admin_apercu_espace(
        "repetiteur",
        SimpleNamespace(),
        SimpleNamespace(),
    )
    contexte = reponse["contexte"]

    assert reponse["template"] == "dashboard_repetiteur.html"
    assert contexte["utilisateur"].role == RoleUtilisateur.REPETITEUR
    assert contexte["utilisateur"].statut_verification_repetiteur == "approuve"
    assert contexte["utilisateur"].id == -1
    assert contexte["statut_repetiteur"] == "approuve"
    assert contexte["utilisateur"].matieres_repetiteur
    assert contexte["utilisateur"].tarif_horaire_repetiteur_ariary == 10000


def test_dashboard_repetiteur_est_independant_du_dashboard_etudiant(monkeypatch):
    utilisateur = SimpleNamespace(
        id=42,
        nom="Répétiteur test",
        role=RoleUtilisateur.REPETITEUR,
        profil_souhaite="repetiteur",
        statut_verification_repetiteur="approuve",
    )
    monkeypatch.setattr(dashboard_router, "utilisateur_courant", lambda *_args: utilisateur)
    appels = _capture_template_dashboard(monkeypatch)

    dashboard_router.page_dashboard(SimpleNamespace(), SimpleNamespace())

    assert appels["template"] == "dashboard_repetiteur.html"
    assert appels["contexte"]["utilisateur"].role == RoleUtilisateur.REPETITEUR


def _capture_template_dashboard(monkeypatch):
    appels = {}

    def rendre(request, template, contexte):
        appels["template"] = template
        appels["contexte"] = contexte
        return appels

    monkeypatch.setattr(dashboard_router.templates, "TemplateResponse", rendre)
    return appels


def test_role_repetiteur_est_different_du_role_sponsor():
    assert RoleUtilisateur.REPETITEUR.value == "repetiteur"
    assert RoleUtilisateur.REPETITEUR != RoleUtilisateur.SPONSOR


def test_apercu_enseignant_est_valide_sans_charger_de_cours_reels(monkeypatch):
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: _admin())
    appels = _capture_template(monkeypatch)

    reponse = admin_router.page_admin_apercu_espace(
        "enseignant",
        SimpleNamespace(),
        SimpleNamespace(),
    )
    contexte = reponse["contexte"]

    assert contexte["statut_enseignant"] == "approuve"
    assert contexte["cours_enseignes"] == []
    assert contexte["statistiques_enseignant"]["cours"] == 0


def test_apercu_etudiant_ne_declenche_pas_les_services_qui_ecrivent_en_base(monkeypatch):
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: _admin())
    _capture_template(monkeypatch)
    session = SimpleNamespace(
        add=lambda *_args: (_ for _ in ()).throw(AssertionError("aucune écriture attendue")),
        commit=lambda: (_ for _ in ()).throw(AssertionError("aucun commit attendu")),
    )

    reponse = admin_router.page_admin_apercu_espace("etudiant", SimpleNamespace(), session)
    contexte = reponse["contexte"]

    assert contexte["gamification"]["total_xp"] == 0
    assert contexte["routine_du_jour"]["total"] == 3
    assert contexte["cercles"] == []
    assert contexte["documents_recents"] == []


def test_espace_apercu_inconnu_revient_au_selecteur(monkeypatch):
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: _admin())
    reponse = admin_router.page_admin_apercu_espace(
        "profil-inconnu",
        SimpleNamespace(),
        SimpleNamespace(),
    )

    assert isinstance(reponse, RedirectResponse)
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/admin/apercus?erreur=espace_invalide"


def test_l_interface_apercu_est_marquee_lecture_seule_et_accessible_depuis_admin():
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    admin = (ROOT / "app" / "templates" / "admin_index.html").read_text(encoding="utf-8")
    selecteur = (ROOT / "app" / "templates" / "admin_apercus.html").read_text(encoding="utf-8")

    assert 'inert data-admin-apercu-contenu' in base
    assert "APERÇU EN LECTURE SEULE" in base
    assert '{% set mode_apercu_admin = mode_apercu_admin|default(false) %}' in base
    assert '{% set mode_apercu_espace = mode_apercu_espace|default("") %}' in base
    assert base.count("0 if mode_apercu_admin else compter_notifications_non_lues(request)") == 4
    assert "none if mode_apercu_admin else request.session.get(\"notification_inactivite\")" in base
    assert 'href="/admin/apercus"' in admin
    assert 'href="/admin/apercus/etudiant"' in selecteur
    assert 'href="/admin/apercus/enseignant"' in selecteur
    assert 'href="/admin/apercus/repetiteur"' in selecteur
    assert "Rôle indépendant" in selecteur
    assert "dashboard_repetiteur.html" in (ROOT / "app" / "routers" / "admin_router.py").read_text(encoding="utf-8")
