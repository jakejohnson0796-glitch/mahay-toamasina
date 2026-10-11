"""Regression guards for language preference placement and circle metadata coherence."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
SIDEBAR_CSS = ROOT / "app" / "static" / "sidebar.css"
CIRCLES_TEMPLATE = ROOT / "app" / "templates" / "cercles_list.html"
CIRCLES_ROUTER = ROOT / "app" / "routers" / "cercles_router.py"
ACADEMIC_ROUTER = ROOT / "app" / "routers" / "academique_router.py"
ACADEMIC = ROOT / "app" / "referentiel_academique.py"


def test_language_selector_is_in_the_preferences_area_not_above_navigation():
    base = BASE.read_text(encoding="utf-8")
    # The template has mutually exclusive authenticated/visitor branches;
    # each rendered page receives exactly one select-langue element.
    assert base.count('id="select-langue"') == 2
    first_selector = base.index('id="select-langue"')
    second_selector = base.index('id="select-langue"', first_selector + 1)
    assert base.index("class=\"tb-menu-compte\"") < first_selector < base.index('id="bouton-theme"')
    assert base.index('href="/inscription"', second_selector - 2500) < second_selector
    assert first_selector > base.index('href="/dashboard" class="tb-sidebar-lien')


def test_language_selector_uses_full_width_accessible_preference_control():
    css = SIDEBAR_CSS.read_text(encoding="utf-8")
    assert ".tb-sidebar-langue {" in css
    assert "grid-template-columns: minmax(0, 1fr)" in css
    assert "width: 100%" in css
    assert "min-height: 2.45rem" in css
    assert ".tb-sidebar-langue select:focus-visible" in css


def test_circle_creation_rejects_partial_academic_metadata():
    router = CIRCLES_ROUTER.read_text(encoding="utf-8")
    assert 'return RedirectResponse("/cercles?erreur=niveau_requis", status_code=303)' in router
    assert 'return RedirectResponse("/cercles?erreur=mention_requise", status_code=303)' in router
    guard = router.index("# Ne jamais transformer silencieusement un choix academique incomplet")
    national_case = router.index("# --- Cas 1 : demande de cercle NATIONAL", guard)
    free_group_creation = router.index("# --- Cas 2 : cercle \"libre\"", national_case)
    assert guard < national_case < free_group_creation


def test_national_parcours_api_rejects_unknown_levels():
    router = ACADEMIC_ROUTER.read_text(encoding="utf-8")
    assert "if niveau and niveau not in NIVEAUX:" in router
    assert "from ..referentiel import NIVEAUX" in router


def test_circle_ui_shows_explicit_type_and_human_level_labels():
    template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
    assert "Cercle national · parcours" in template
    assert "Cercle national · tronc commun" in template
    assert "Groupe libre" in template
    assert "niveaux_libelles.get(info.cercle.niveau" in template
    assert "niveaux_libelles.get(n, n)" in template
    assert 'class="carte-claire-avatar carte-claire-avatar-couleur-' in template


def test_legacy_circle_type_uses_effective_mention_and_checks_conflicts():
    academic = ACADEMIC.read_text(encoding="utf-8")
    assert "def type_cercle(" in academic
    assert "mention_id_effectif = cercle.mention_id" in academic
    assert "filiere.mention_id != mention_id_effectif" in academic
    assert "def profil_correspond_au_cercle(" in academic
    assert "mention_effective_sql = func.coalesce(" in academic
