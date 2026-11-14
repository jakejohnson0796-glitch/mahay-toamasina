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

    request = SimpleNamespace(query_params=SimpleNamespace(get=lambda *_args: ""))
    session = SimpleNamespace(exec=lambda *_args: SimpleNamespace(all=lambda: []))
    reponse = admin_router.page_admin_apercus(request, session)

    assert reponse["template"] == "admin_apercus.html"
    assert reponse["contexte"]["utilisateur"].role == RoleUtilisateur.ADMIN
    assert reponse["contexte"]["comptes_reels"] == []


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

    dashboard_router.page_dashboard(
        SimpleNamespace(),
        SimpleNamespace(exec=lambda *_args: SimpleNamespace(all=lambda: [])),
    )

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



def test_dashboard_revient_a_l_espace_etudiant_apres_retrait_du_role_repetiteur(monkeypatch):
    utilisateur = SimpleNamespace(
        id=42,
        nom="Ancien répétiteur",
        role=RoleUtilisateur.ETUDIANT,
        profil_souhaite="repetiteur",
        statut_verification_repetiteur="retire",
    )
    monkeypatch.setattr(dashboard_router, "utilisateur_courant", lambda *_args: utilisateur)
    appels = _capture_template_dashboard(monkeypatch)
    monkeypatch.setattr(
        dashboard_router.dashboard_module,
        "notifier_echeances_proches",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        dashboard_router.dashboard_module,
        "donnees_dashboard",
        lambda *_args: {},
    )

    dashboard_router.page_dashboard(SimpleNamespace(), SimpleNamespace())

    assert appels["template"] == "dashboard_etudiant.html"


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


def test_admin_peut_ouvrir_un_compte_reel_sans_perdre_son_identite(monkeypatch):
    admin = _admin()
    cible = SimpleNamespace(
        id=42,
        nom="Compte élève",
        role=RoleUtilisateur.ETUDIANT,
        banni=False,
    )
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: admin)
    monkeypatch.setattr(
        admin_router,
        "empreinte_session_utilisateur",
        lambda utilisateur: f"fingerprint-{utilisateur.id}",
    )
    evenements = []
    session = SimpleNamespace(
        get=lambda _model, identifiant: cible if identifiant == cible.id else admin,
        add=evenements.append,
        commit=lambda: None,
    )
    request = SimpleNamespace(session={"user_id": admin.id, "auth_fingerprint": "fingerprint-7"})

    reponse = admin_router.ouvrir_espace_reel_utilisateur(request, cible.id, session)

    assert isinstance(reponse, RedirectResponse)
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/dashboard"
    assert request.session["user_id"] == cible.id
    assert request.session["admin_mode_actor_id"] == admin.id
    assert request.session["admin_mode_target_id"] == cible.id
    assert request.session["admin_mode_actor_fingerprint"] == "fingerprint-7"
    assert request.session["auth_fingerprint"] == "fingerprint-42"
    assert evenements[0].admin_id == admin.id
    assert evenements[0].utilisateur_cible_id == cible.id


def test_admin_peut_quitter_le_compte_reel_et_retrouver_sa_session(monkeypatch):
    admin = _admin()
    monkeypatch.setattr(
        admin_router,
        "empreinte_session_utilisateur",
        lambda utilisateur: f"fingerprint-{utilisateur.id}",
    )
    request = SimpleNamespace(session={
        "user_id": 42,
        "auth_fingerprint": "fingerprint-42",
        "admin_mode_actor_id": admin.id,
        "admin_mode_actor_fingerprint": "fingerprint-7",
        "admin_mode_target_id": 42,
        "_csrf_token": "ancien",
    })
    session = SimpleNamespace(get=lambda _model, identifiant: admin if identifiant == admin.id else None)

    reponse = admin_router.quitter_espace_reel_utilisateur(request, session)

    assert isinstance(reponse, RedirectResponse)
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/admin/apercus"
    assert request.session["user_id"] == admin.id
    assert request.session["auth_fingerprint"] == "fingerprint-7"
    assert "_csrf_token" in request.session
    assert "admin_mode_actor_id" not in request.session
    assert "admin_mode_target_id" not in request.session


def test_admin_ne_peut_pas_ouvrir_un_compte_banni_ou_un_role_hors_perimetre(monkeypatch):
    admin = _admin()
    cible = SimpleNamespace(
        id=88,
        nom="Compte interdit",
        role=RoleUtilisateur.SPONSOR,
        banni=False,
    )
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: admin)
    session = SimpleNamespace(
        get=lambda *_args: cible,
        add=lambda *_args: (_ for _ in ()).throw(AssertionError("aucun journal attendu")),
        commit=lambda: (_ for _ in ()).throw(AssertionError("aucun commit attendu")),
    )
    request = SimpleNamespace(session={"user_id": admin.id, "auth_fingerprint": "fingerprint-7"})

    reponse = admin_router.ouvrir_espace_reel_utilisateur(request, cible.id, session)

    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/admin/apercus?erreur=compte_indisponible"
    assert request.session.get("admin_mode_actor_id") is None


def test_mode_admin_reel_affiche_un_bandeau_et_ne_bloque_pas_l_interface():
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    script = (ROOT / "app" / "static" / "js" / "admin-confirmation.js").read_text(encoding="utf-8")
    selecteur = (ROOT / "app" / "templates" / "admin_apercus.html").read_text(encoding="utf-8")

    assert "MODE ADMINISTRATEUR ACTIF" in base
    assert 'data-admin-mode-actif="1"' in base
    assert 'action="/admin/apercus/quitter"' in base
    assert "data-admin-mode-actif === \"1\"" in script
    assert 'action="/admin/apercus/acceder"' in selecteur
    assert "mes actions seront réelles" in selecteur
