"""Regression checks for the global language selector placement and accessibility."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
PREFERENCES_CSS = ROOT / "app" / "static" / "preferences-toolbar.css"
LANGUAGE_JS = ROOT / "app" / "static" / "js" / "langue.js"


def test_language_selector_is_a_global_singleton_outside_the_sidebar():
    base = BASE.read_text(encoding="utf-8")
    assert base.count('id="select-langue"') == 1
    assert base.index("</aside>") < base.index('class="gm-preferences-toolbar"')
    assert base.index('class="gm-preferences-toolbar"') < base.index('class="mobile-entete-app"')
    assert "tb-sidebar-langue-entete" not in base
    assert 'for="select-langue" data-langue-label' in base
    assert '<option value="fr">Français</option>' in base
    assert '<option value="mg">Malagasy</option>' in base
    assert "/static/preferences-toolbar.css?v={{ version_asset('preferences-toolbar.css') }}" in base


def test_language_selector_keeps_the_existing_translation_script_contract():
    base = BASE.read_text(encoding="utf-8")
    script = LANGUAGE_JS.read_text(encoding="utf-8")
    assert "/static/js/langue.js?v={{ version_asset('js/langue.js') }}" in base
    assert 'var SELECTEUR = "#select-langue";' in script
    assert 'selecteur.addEventListener("change"' in script
    assert "localStorage.setItem(CLE_LANGUE, langueActuelle)" in script


def test_language_selector_has_keyboard_focus_and_responsive_toolbar_styles():
    css = PREFERENCES_CSS.read_text(encoding="utf-8")
    assert ".gm-language-control select:focus-visible" in css
    assert "@media (max-width: 900px)" in css
    assert "@media (max-width: 420px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    depth = 0
    for char in css:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "CSS contains an unmatched closing brace"
    assert depth == 0, "CSS contains an unmatched opening brace"
