from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
ROUTER = ROOT / "app" / "routers" / "dashboard_router.py"
SCRIPT = ROOT / "app" / "static" / "js" / "bilan-reprise.js"
STYLE = ROOT / "app" / "static" / "bilan-reprise.css"
SERVICE = ROOT / "app" / "learning_recap.py"


def test_bilan_est_charge_uniquement_pour_les_sessions_authentifiees():
    base = BASE.read_text(encoding="utf-8")
    assert '{% if request.session.get("user_id") %}' in base
    assert 'id="bilan-reprise-fond"' in base
    assert 'data-user-key="{{ request.session.get(\'user_id\') }}"' in base
    assert 'id="bilan-reprise-dialogue"' in base
    assert 'role="dialog"' in base
    assert 'aria-modal="true"' in base
    assert "version_asset('bilan-reprise.css')" in base
    assert "version_asset('js/bilan-reprise.js')" in base


def test_api_du_bilan_est_authentifiee_et_sans_cache():
    router = ROUTER.read_text(encoding="utf-8")
    assert '@router.get("/api/apprentissage/bilan-reprise")' in router
    assert "utilisateur_courant(request, session)" in router
    assert 'status_code=401' in router
    assert 'headers={"Cache-Control": "no-store"}' in router
    assert '"Cache-Control": "no-store"' in router
    assert "learning_recap.construire_bilan" in router


def test_bilan_reprise_evite_une_modale_a_chaque_actualisation_et_separe_les_comptes():
    script = SCRIPT.read_text(encoding="utf-8")
    assert "3 * 60 * 60 * 1000" in script
    assert "dateLocaleKey" in script
    assert "sessionStorage.getItem(KEY_TAB)" in script
    assert 'var prefix = "mitaridala:bilan-reprise:v1:" + userKey + ":";' in script
    assert "KEY_SUMMARY_FOR" in script
    assert "KEY_LOCK" in script
    assert "credentials: \"same-origin\"" in script
    assert 'event.key === "Escape"' in script
    assert "event.key !== \"Tab\"" in script


def test_rendu_du_bilan_n_injecte_pas_le_contenu_utilisateur_comme_html():
    script = SCRIPT.read_text(encoding="utf-8")
    assert "function creerElement" in script
    assert "element.textContent = String(contenu)" in script
    assert ".innerHTML" not in script
    assert "data-no-translate" in BASE.read_text(encoding="utf-8")


def test_bilan_est_responsive_accessible_et_respecte_le_mode_sombre():
    style = STYLE.read_text(encoding="utf-8")
    assert 'html[data-theme="sombre"] .bilan-reprise-dialogue' in style
    assert "@media (max-width: 780px)" in style
    assert "@media (max-width: 480px)" in style
    assert "@media (prefers-reduced-motion: reduce)" in style
    assert ":focus-visible" in style
    assert "overscroll-behavior: contain" in style


def test_bilan_utilise_des_traces_reelles_et_ne_depend_pas_d_une_generation_ia():
    service = SERVICE.read_text(encoding="utf-8")
    for modele in ("TentativeQuiz", "ProgressionNotion", "ConsultationDocument", "SessionTuteur", "JeuCerebralSession", "MissionApprentissage"):
        assert modele in service
    assert "def construire_bilan(" in service
    assert "generer_reponse_tuteur" not in service
    assert "OpenAI" not in service
    assert "Groq" not in service
    assert 'ActionGamification.action.in_(("cercle", "cercle_rejoint", "classe", "document"))' in service
