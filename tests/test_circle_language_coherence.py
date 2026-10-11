"""Regression checks for language placement and academic circle coherence."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
CIRCLES = ROOT / "app" / "templates" / "cercles_list.html"
CIRCLE_ROUTER = ROOT / "app" / "routers" / "cercles_router.py"
ACADEMIC_ROUTER = ROOT / "app" / "routers" / "academique_router.py"
ACADEMIC_LOGIC = ROOT / "app" / "referentiel_academique.py"
CIRCLE_JS = ROOT / "app" / "static" / "js" / "cercles-list.js"
POLISH_CSS = ROOT / "app" / "static" / "navigation-circles-polish.css"


def test_language_selector_is_unique_and_inside_bottom_preferences_area():
    base = BASE.read_text(encoding="utf-8")
    assert base.count('id="select-langue"') == 1
    assert base.count('/static/navigation-circles-polish.css') == 1
    assert 'class="tb-sidebar-preferences"' in base
    assert base.index('class="tb-sidebar-preferences"') < base.index('id="select-langue"')
    assert base.index('id="select-langue"') < base.index("</aside>")
    assert base.index("class=\"tb-sidebar-nav\"") < base.index('class="tb-sidebar-preferences"')
    assert 'aria-label="Choisir la langue du site"' in base


def test_preferences_css_is_compact_responsive_and_keyboard_accessible():
    css = POLISH_CSS.read_text(encoding="utf-8")
    assert ".tb-sidebar-preferences .tb-sidebar-langue" in css
    assert "@media (min-width: 901px)" in css
    assert "body.sidebar-compact .tb-sidebar-preferences .tb-sidebar-langue label" in css
    assert ":focus-visible" in css
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_circle_cards_use_one_canonical_academic_identity():
    template = CIRCLES.read_text(encoding="utf-8")
    router = CIRCLE_ROUTER.read_text(encoding="utf-8")
    logic = ACADEMIC_LOGIC.read_text(encoding="utf-8")
    assert "info.cercle.niveau" not in template
    assert "info.niveau_effectif" in template
    assert "Parcours national" in template
    assert "Tronc commun" in template
    assert "Groupe libre" in template
    assert "identite_cercle(cercle, session)" in router
    assert "def identite_cercle(" in logic
    assert 'return "libre"' in logic


def test_partial_academic_circle_creation_is_rejected_server_side():
    router = CIRCLE_ROUTER.read_text(encoding="utf-8")
    template = CIRCLES.read_text(encoding="utf-8")
    js = CIRCLE_JS.read_text(encoding="utf-8")
    assert "demande_nationale = bool(mention_id_nettoye or filiere_id_nettoye or niveau_nettoye)" in router
    assert 'erreur=niveau_requis' in router
    assert 'erreur=mention_requise' in router
    assert 'erreur=mention_parcours_incoherent' in router
    assert "mention.required = Boolean(niveau.value || parcours.value)" in js
    assert "niveau.required = Boolean(mention.value || parcours.value)" in js
    assert 'id="creation-info-tronc-commun" hidden aria-live="polite"' in template


def test_national_program_list_prefers_level_specific_filiere_and_checks_codes():
    router = ACADEMIC_ROUTER.read_text(encoding="utf-8")
    assert "if niveau and niveau not in NIVEAUX:" in router
    assert "filieres.sort(key=lambda f: (f.niveau is None, f.nom.casefold(), f.id or 0))" in router
    assert "ProgrammeUniversitaire.universite_id == Faculte.universite_id" in router


def test_navigation_circle_css_braces_are_balanced():
    css = POLISH_CSS.read_text(encoding="utf-8")
    depth = 0
    for char in css:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "CSS contains an unmatched closing brace"
    assert depth == 0, "CSS contains an unmatched opening brace"
