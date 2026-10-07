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
    assert 'CACHE_NOM = "mahay-static-v2"' in sw
    assert 'self.clients.claim()' in sw
