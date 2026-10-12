"""Regression checks for language preferences and circle taxonomy consistency."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
SIDEBAR_CSS = ROOT / "app" / "static" / "sidebar.css"
CIRCLES_TEMPLATE = ROOT / "app" / "templates" / "cercles_list.html"
CIRCLES_ROUTER = ROOT / "app" / "routers" / "cercles_router.py"
ACADEMIC_ROUTER = ROOT / "app" / "routers" / "academique_router.py"
ACADEMIC_REFERENCE = ROOT / "app" / "referentiel_academique.py"


def test_language_selector_lives_below_navigation_and_exists_once():
    base = BASE.read_text(encoding="utf-8")
    sidebar = base.split('<aside class="tb-sidebar"', 1)[1].split("</aside>", 1)[0]
    assert sidebar.count('id="select-langue"') == 1
    selector_pos = sidebar.index('<section class="tb-sidebar-langue"')
    assert selector_pos > sidebar.rfind("</nav>")
    assert "FR · MG" in sidebar
    assert 'data-langue-label>Langue<' in sidebar
    assert 'option value="fr">Français' in sidebar
    assert 'option value="mg">Malagasy' in sidebar


def test_language_preference_card_is_visible_responsive_and_keyboard_accessible():
    css = SIDEBAR_CSS.read_text(encoding="utf-8")
    assert "Panneau de langue aligné avec les réglages" in css
    assert "linear-gradient(135deg, rgba(255,255,255,.07)" in css
    assert ".tb-sidebar-langue select:focus-visible" in css
    assert "body.sidebar-compact .tb-sidebar-langue" in css
    assert "@media (max-width: 900px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_circle_labels_use_national_scope_and_human_readable_levels():
    template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
    assert "À l’échelle de Madagascar · Cercles d’étude" in template
    assert 'niveaux_libelles.get(n, n)' in template
    assert 'niveaux_libelles.get(info.cercle.niveau, info.cercle.niveau)' in template
    assert "Parcours national" in template
    assert "Tronc commun" in template
    assert "Référentiel à vérifier" in template
    assert 'class="carte-claire-avatar carte-claire-avatar-couleur-' in template
    assert '<span class="carte-claire-avatar" aria-hidden="true" class=' not in template


def test_creation_route_rejects_partial_or_cross_mention_selections():
    router = CIRCLES_ROUTER.read_text(encoding="utf-8")
    assert "erreur_selection_creation_cercle(" in router
    assert "erreur=parcours_hors_mention" in router
    assert "niveaux_libelles" in router
    assert "type_cercle(cercle, session)" in router
    assert "cercle_est_national(cercle, session)" in router
    assert 'type_cercle(cercle, session) != "libre"' in router


def test_national_course_options_match_the_actual_university_of_the_faculty():
    router = ACADEMIC_ROUTER.read_text(encoding="utf-8")
    assert "Faculte.universite_id == ProgrammeUniversitaire.universite_id" in router
    assert "if not domaine or not domaine.est_active:" in router
    assert "Domaine.est_active == True" in router


def test_legacy_circle_type_is_resolved_from_filiere_and_conflicts_stay_incomplete():
    reference = ACADEMIC_REFERENCE.read_text(encoding="utf-8")
    assert "def type_cercle(cercle: CercleEtude, session: Optional[Session] = None)" in reference
    assert "mention_id = mention_id or filiere.mention_id" in reference
    assert "mention_id != filiere.mention_id" in reference
    assert "def erreur_selection_creation_cercle(" in reference
    assert "mention_compatible_avec_parcours" in reference


def test_circle_filter_css_braces_are_balanced():
    template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
    block = template.split("<style nonce=", 1)[1].split("</style>", 1)[0]
    depth = 0
    for char in block:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "Circle page styles contain an unmatched closing brace"
    assert depth == 0, "Circle page styles contain an unmatched opening brace"
