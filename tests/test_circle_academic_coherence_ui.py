"""Regression checks for professional language controls and study-circle coherence."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
CSS = ROOT / "app" / "static" / "site-academic-polish.css"
SIDEBAR = ROOT / "app" / "static" / "sidebar.css"
CIRCLES = ROOT / "app" / "templates" / "cercles_list.html"
CIRCLE_JS = ROOT / "app" / "static" / "js" / "cercles-list.js"
CIRCLE_ROUTER = ROOT / "app" / "routers" / "cercles_router.py"
ACADEMIC_ROUTER = ROOT / "app" / "routers" / "academique_router.py"


def test_language_selector_is_single_global_topbar_control_not_sidebar_block():
    base = BASE.read_text(encoding="utf-8")
    assert base.count('id="select-langue"') == 1
    assert 'class="app-toolbar"' in base
    assert 'class="app-toolbar-langue"' in base
    assert base.index('class="app-toolbar"') < base.index('<main class=')
    assert "tb-sidebar-langue" not in base


def test_language_topbar_is_responsive_and_theme_aware():
    css = CSS.read_text(encoding="utf-8")
    assert ".app-toolbar-langue" in css
    assert "@media (max-width: 700px)" in css
    assert "var(--content-surface" in css
    assert "focus-visible" in css
    depth = 0
    for char in css:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "CSS contains an unmatched closing brace"
    assert depth == 0, "CSS contains an unmatched opening brace"


def test_sidebar_does_not_render_or_style_the_old_large_language_card():
    base = BASE.read_text(encoding="utf-8")
    # The legacy CSS can remain for backwards cache compatibility, but no
    # rendered template uses it after the move to the application utility bar.
    assert "tb-sidebar-langue" not in base


def test_network_failure_is_not_misread_as_a_real_tronc_commun():
    js = CIRCLE_JS.read_text(encoding="utf-8")
    assert "if (!response.ok) return null" in js
    assert "return Array.isArray(data) ? data : null" in js
    assert "if (rows === null)" in js
    assert 'parcours.dataset.parcoursCharge = "false"' in js
    assert 'option(parcours, "tronc_commun"' in js
    assert 'parcours.dataset.parcoursCharge !== "true"' in js


def test_new_national_circles_require_a_complete_academic_identity():
    router = CIRCLE_ROUTER.read_text(encoding="utf-8")
    template = CIRCLES.read_text(encoding="utf-8")
    assert "identite_academique_demandee" in router
    assert "identite_academique_incomplete" in router
    assert "parcours_mention_incoherents" in router
    assert 'request.query_params.get("erreur") == "identite_academique_incomplete"' in template
    assert 'request.query_params.get("erreur") == "parcours_mention_incoherents"' in template


def test_national_pathway_api_validates_level_and_active_university_offer():
    router = ACADEMIC_ROUTER.read_text(encoding="utf-8")
    assert "if niveau and niveau not in NIVEAUX:" in router
    assert "Universite.est_active == True" in router
    assert "ProgrammeUniversitaire.universite_id == Faculte.universite_id" in router
    assert '"niveau": f.niveau' in router


def test_circle_cards_use_human_labels_and_one_valid_avatar_class_attribute():
    template = CIRCLES.read_text(encoding="utf-8")
    assert "Cercle de parcours" in template
    assert "Tronc commun" in template
    assert "Référentiel à vérifier" in template
    assert 'class="carte-claire-avatar carte-claire-avatar-couleur-{{ info.cercle.id % 5 }}"' in template
    assert 'aria-hidden="true" class="carte-claire-avatar-couleur-' not in template
    assert "{{ info.niveau_effectif }}" in template
