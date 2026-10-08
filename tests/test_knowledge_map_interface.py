from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_carte_connaissances_est_exposee_et_reliee_aux_revisions():
    router = (ROOT / "app/routers/revisions_router.py").read_text(encoding="utf-8")
    template = (ROOT / "app/templates/carte_connaissances.html").read_text(encoding="utf-8")
    revisions = (ROOT / "app/templates/mes_revisions.html").read_text(encoding="utf-8")

    assert '@router.get("/carte-connaissances")' in router
    assert 'knowledge_map.construire_carte' in router
    assert 'knowledge-map' in template
    assert 'href="/carte-connaissances"' in revisions


def test_carte_connaissances_conserve_les_actions_csrf_et_ciblees():
    template = (ROOT / "app/templates/carte_connaissances.html").read_text(encoding="utf-8")

    assert 'name="_csrf"' in template
    assert 'action="/quiz/cible"' in template
    assert 'progression_id' in template
    assert 'action="/tuteur/demander"' in template


def test_styles_carte_connaissances_sont_responsifs():
    css = (ROOT / "app/static/student-hub.css").read_text(encoding="utf-8")

    assert ".knowledge-map-grid" in css
    assert ".knowledge-blockers" in css
    assert ".knowledge-summary-grid" in css
    assert "@media(max-width:760px)" in css
