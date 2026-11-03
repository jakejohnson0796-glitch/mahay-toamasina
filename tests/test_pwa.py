from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_service_worker_est_servi_a_la_racine_et_autorise_le_scope_global():
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert '@app.get("/sw.js", include_in_schema=False)' in main
    assert '"Service-Worker-Allowed": "/"' in main
    assert 'read_text(encoding="utf-8")' in main


def test_base_enregistre_la_pwa():
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    assert 'href="/static/manifest.json"' in base
    assert '/static/js/pwa.js' in base


def test_service_worker_ne_met_pas_les_pages_dynamiques_en_cache():
    sw = (ROOT / "app" / "static" / "sw.js").read_text(encoding="utf-8")
    assert 'url.pathname.startsWith("/static/")' in sw
    assert 'requete.method !== "GET"' in sw
    assert 'CACHE_NOM = "mahay-static-v3"' in sw
    assert 'self.clients.claim()' in sw



def test_un_seul_service_worker_est_enregistre_a_la_racine():
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    pwa = (ROOT / "app" / "static" / "js" / "pwa.js").read_text(encoding="utf-8")

    # pwa.js utilise l'endpoint sans cache /sw.js avec le scope global.
    # base.html ne doit pas créer en plus une seconde registration /static/.
    assert 'navigator.serviceWorker.register("/sw.js", { scope: "/" })' in pwa
    assert "navigator.serviceWorker.register('/static/sw.js')" not in base


def test_service_worker_rotates_old_static_cache_after_release():
    sw = (ROOT / "app" / "static" / "sw.js").read_text(encoding="utf-8")
    assert 'cle.startsWith("mahay-static-") && cle !== CACHE_NOM' in sw
    assert 'self.clients.claim()' in sw
    assert 'self.skipWaiting()' in sw


def test_brouillon_quiz_est_isole_et_ne_stocke_pas_de_jeton():
    pwa = (ROOT / "app" / "static" / "js" / "pwa.js").read_text(encoding="utf-8")
    quiz = (ROOT / "app" / "templates" / "quiz_passer.html").read_text(encoding="utf-8")

    assert 'data-quiz-owner="{{ tentative.utilisateur_id }}"' in quiz
    assert 'data-quiz-mode-examen="{{ \'1\' if tentative.mode_examen else \'0\' }}"' in quiz
    assert "data-quiz-draft-status" in quiz
    assert "data-quiz-draft-clear" in quiz
    assert "mitaridala:quiz-draft:v1:" in pwa
    assert 'form.dataset.quizAdaptatif === "1"' in pwa
    assert 'form.dataset.quizModeExamen === "1"' in pwa
    assert "_csrf" not in pwa


def test_ci_verifie_la_syntaxe_et_le_comportement_du_brouillon():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "node --check app/static/js/pwa.js" in workflow
    assert "node scripts/smoke_quiz_draft.mjs" in workflow
