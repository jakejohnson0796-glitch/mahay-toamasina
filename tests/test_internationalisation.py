from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_selecteur_malagasy_present_pour_visiteurs_et_membres():
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    assert '<select id="select-langue" name="langue"' in base
    assert '<option value="fr">Français</option>' in base
    assert '<option value="mg">Malagasy</option>' in base
    assert 'src="/static/js/langue.js?' in base
    assert 'lang="fr"' in base


def test_traduction_ne_depend_d_aucun_service_tiers_et_protege_le_contenu_ia():
    js = (ROOT / "app" / "static" / "js" / "langue.js").read_text(encoding="utf-8")
    assert 'localStorage' in js
    assert '"mahay-langue"' in js
    assert '"[data-rendu]"' in js
    assert '".ai-rendered-content"' in js
    assert "TRADUCTIONS_MG" in js
    assert "fetch(" not in js
    assert "XMLHttpRequest" not in js


def test_styles_du_selecteur_sont_compatibles_avec_la_sidebar_compacte():
    css = (ROOT / "app" / "static" / "sidebar.css").read_text(encoding="utf-8")
    assert ".tb-sidebar-langue" in css
    assert "body.sidebar-compact .tb-sidebar-langue" in css
    assert "body.sidebar-compact .tb-sidebar-langue label" in css


def test_ci_lance_le_test_navigateur_du_selecteur_de_langue():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "node scripts/smoke_language_switcher.mjs" in workflow
