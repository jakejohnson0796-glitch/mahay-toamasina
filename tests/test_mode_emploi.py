from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mode_emploi_route_est_enregistre():
    source = (ROOT / "app" / "routers" / "mode_emploi_router.py").read_text(encoding="utf-8")
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert '@router.get("/mode-emploi")' in source
    assert "app.include_router(mode_emploi_router.router)" in main


def test_mode_emploi_contient_les_parcours_principaux():
    template = (ROOT / "app" / "templates" / "mode_emploi.html").read_text(encoding="utf-8")
    for identifiant in (
        'id="demarrage"',
        'id="navigation"',
        'id="documents"',
        'id="apprendre"',
        'id="cercles"',
        'id="classe"',
        'id="compte"',
        'id="depannage"',
    ):
        assert identifiant in template
    assert 'class="mode-emploi-quickstart"' in template
    assert 'class="mode-emploi-ai-access' in template
    assert "14 jours" in template
    assert "60 jours" in template
    assert "34 37 795 52" not in template



def test_onglet_mode_emploi_visible_dans_la_navigation():
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    assert 'href="/mode-emploi"' in base
    assert 'Mode d\'emploi' in base


def test_mode_emploi_n_utilise_pas_de_style_inline():
    template = (ROOT / "app" / "templates" / "mode_emploi.html").read_text(encoding="utf-8")
    assert ' style="' not in template
