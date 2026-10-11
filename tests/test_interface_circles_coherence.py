"""Regression checks for the global language control and circle coherence."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
SIDEBAR_CSS = ROOT / "app" / "static" / "sidebar.css"
POLISH_CSS = ROOT / "app" / "static" / "interface-circles-polish.css"
CIRCLE_JS = ROOT / "app" / "static" / "js" / "cercles-list.js"
CIRCLE_ROUTER = ROOT / "app" / "routers" / "cercles_router.py"
ACADEMIC_ROUTER = ROOT / "app" / "routers" / "academique_router.py"
ACADEMIC = ROOT / "app" / "referentiel_academique.py"
ADMIN_ROUTER = ROOT / "app" / "routers" / "admin_referentiel_router.py"


def test_language_selector_is_unique_and_outside_the_sidebar():
    base = BASE.read_text(encoding="utf-8")
    sidebar_css = SIDEBAR_CSS.read_text(encoding="utf-8")
    assert base.count('id="select-langue"') == 1
    assert 'data-langue-label>Langue</label>' in base
    assert "tb-sidebar-langue" not in base
    assert "tb-sidebar-langue" not in sidebar_css
    assert 'class="gm-language-toolbar"' in base
    assert 'href="/static/interface-circles-polish.css?v={{ version_asset(\'interface-circles-polish.css\') }}"' in base
    assert base.index("/static/motion-polish.css") < base.index("/static/interface-circles-polish.css") < base.index("</head>")


def test_language_toolbar_is_responsive_accessible_and_theme_aware():
    css = POLISH_CSS.read_text(encoding="utf-8")
    for token in (
        ".gm-language-toolbar",
        ".gm-language-control",
        ".gm-language-control select",
        ".gm-language-control select:focus-visible",
        "@media (max-width: 900px)",
        "@media (max-width: 390px)",
        "var(--content-surface)",
        "var(--content-text)",
        "@media (prefers-reduced-motion: reduce)",
    ):
        assert token in css, token


def test_circle_cascade_discards_stale_parcours_responses():
    js = CIRCLE_JS.read_text(encoding="utf-8")
    assert 'domaine.addEventListener("change"' in js
    assert 'mention.addEventListener("change"' in js
    assert js.count("generation += 1;") >= 2
    assert "if (ticket !== generation) return;" in js


def test_circle_filters_and_cards_use_the_linked_pathway_as_source_of_truth():
    router = CIRCLE_ROUTER.read_text(encoding="utf-8")
    assert router.count("func.coalesce(Filiere.mention_id, CercleEtude.mention_id)") >= 3
    assert router.count('referentiel_academique.type_cercle(cercle, filiere)') >= 2
    assert "filiere_cercle = session.get(Filiere, cercle.filiere_id) if cercle.filiere_id else None" in router
    assert 'f"\/cercles/{cercle_id}/membres?erreur=referentiel_a_verifier"' in router


def test_national_pathway_endpoint_scopes_active_offers_to_the_pathways_university():
    router = ACADEMIC_ROUTER.read_text(encoding="utf-8")
    assert ".join(Faculte, Faculte.id == Filiere.faculte_id)" in router
    assert "ProgrammeUniversitaire.universite_id == Faculte.universite_id" in router
    assert 'elif niveau and f.niveau == niveau and precedente["niveau"] != niveau:' in router


def test_reference_validation_rejects_mixed_levels_and_inconsistent_mentions():
    academic = ACADEMIC.read_text(encoding="utf-8")
    admin = ADMIN_ROUTER.read_text(encoding="utf-8")
    assert "def type_cercle(cercle: CercleEtude, filiere: Optional[Filiere] = None)" in academic
    assert "if cercle.mention_id and cercle.mention_id != filiere.mention_id:" in academic
    assert "if filiere.niveau is not None and filiere.niveau != cercle.niveau:" in academic
    assert "filiere_canonique_pour_cercle(session, filiere, cercle.niveau)" in admin
    assert "session, filiere_demandee, demande.niveau" in admin


def test_interface_circle_css_braces_are_balanced():
    css = POLISH_CSS.read_text(encoding="utf-8")
    depth = 0
    for char in css:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "CSS contains an unmatched closing brace"
    assert depth == 0, "CSS contains an unmatched opening brace"
