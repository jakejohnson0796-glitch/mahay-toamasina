"""Regression checks for the language toolbar and coherent circle hierarchy."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
SIDEBAR_CSS = ROOT / "app" / "static" / "sidebar.css"
PREFERENCES_CSS = ROOT / "app" / "static" / "preferences-toolbar.css"
CIRCLES_TEMPLATE = ROOT / "app" / "templates" / "cercles_list.html"
CIRCLES_ROUTER = ROOT / "app" / "routers" / "cercles_router.py"
CIRCLES_JS = ROOT / "app" / "static" / "js" / "cercles-list.js"
ACADEMIC_API = ROOT / "app" / "routers" / "academique_router.py"
ACADEMIC_SERVICE = ROOT / "app" / "referentiel_academique.py"


def test_language_selector_is_unique_and_outside_the_navigation_sidebar():
    base = BASE.read_text(encoding="utf-8")
    assert base.count('id="select-langue"') == 1
    assert "gm-preferences-toolbar" in base
    sidebar_end = base.index("</aside>")
    app_page = base.index('<div class="app-page">')
    toolbar = base.index('class="gm-preferences-toolbar"')
    mobile_header = base.index('class="mobile-entete-app"')
    # Keep the toolbar in the page's flex column, not as an extra grid sibling.
    assert sidebar_end < app_page < toolbar < mobile_header
    assert "tb-sidebar-langue" not in base
    assert '/static/preferences-toolbar.css?v={{ version_asset(\'preferences-toolbar.css\') }}' in base


def test_language_toolbar_is_responsive_accessible_and_has_no_duplicate_state():
    css = PREFERENCES_CSS.read_text(encoding="utf-8")
    assert ".gm-language-control select" in css
    assert ".gm-language-control select:focus-visible" in css
    assert "@media (max-width: 900px)" in css
    assert "@media (max-width: 420px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    sidebar = SIDEBAR_CSS.read_text(encoding="utf-8")
    assert "tb-sidebar-langue" not in sidebar


def test_circle_cards_use_explicit_hierarchy_labels_and_readable_level_names():
    template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
    assert "Parcours national" in template
    assert "Tronc commun" in template
    assert "Groupe libre" in template
    assert "niveaux_libelles.get(n, n)" in template
    assert "niveaux_libelles.get(info.cercle.niveau, info.cercle.niveau)" in template
    assert 'class="carte-claire-avatar carte-claire-avatar-couleur-{{ info.cercle.id % 5 }}"' in template
    assert '"Domaine non renseigne"' not in template


def test_circle_creation_does_not_silently_downgrade_incomplete_academic_choices():
    router = CIRCLES_ROUTER.read_text(encoding="utf-8")
    assert 'erreur=niveau_requis' in router
    assert 'erreur=mention_requise' in router
    assert 'erreur=parcours_mention_incoherente' in router
    assert "mention_id_nettoye != filiere.mention_id" in router
    assert "niveau_nettoye not in NIVEAUX" in router
    assert "(mention_id_nettoye or filiere_id_nettoye) and not niveau_nettoye" in router
    assert 'filiere_id == "tronc_commun"' in router
    assert 'filiere_id != "tronc_commun" and filiere_id_nettoye is None' in router
    assert 'erreur=tronc_commun_indisponible' in router


def test_circle_program_selector_and_available_filter_use_coherent_references():
    api = ACADEMIC_API.read_text(encoding="utf-8")
    service = ACADEMIC_SERVICE.read_text(encoding="utf-8")
    assert ".join(Faculte, Faculte.id == Filiere.faculte_id)" in api
    assert "ProgrammeUniversitaire.universite_id == Faculte.universite_id" in api
    assert "def type_cercle_avec_filiere(" in service
    assert "def cercle_est_national_avec_filiere(" in service
    assert "mention_effective_sql == mention_id" in service
    assert "mentions_coherentes" in service


def test_circle_cascade_distinguishes_empty_results_from_api_failure():
    js = CIRCLES_JS.read_text(encoding="utf-8")
    assert "if (!response.ok) return null" in js
    assert "return Array.isArray(data) ? data : null" in js
    assert "if (rows === null)" in js
    assert "Référentiel indisponible — réessaie" in js
    assert "dataset.erreurChargement" in js
    assert "niveau_a_confirmer" in js


def test_circle_creation_presents_common_core_as_an_explicit_choice():
    js = CIRCLES_JS.read_text(encoding="utf-8")
    assert 'option(parcours, "tronc_commun", "Tronc commun (sans parcours spécifique)"' in js
    assert "parcours.required = true" in js
    assert "aucun classement par défaut ne sera appliqué" in js


def test_circle_stylesheet_is_valid_css_with_balanced_blocks():
    css = PREFERENCES_CSS.read_text(encoding="utf-8")
    depth = 0
    for char in css:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "CSS contains an unmatched closing brace"
    assert depth == 0, "CSS contains an unmatched opening brace"
