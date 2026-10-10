from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
HOME = ROOT / "app" / "templates" / "index.html"
REFRESH = ROOT / "app" / "static" / "experience-refresh.css"


def test_visual_refresh_is_loaded_after_responsive_foundations():
    base = BASE.read_text(encoding="utf-8")
    responsive = base.index("/static/responsive-overrides.css")
    refresh_ref = '/static/experience-refresh.css?v={{ version_asset(\'experience-refresh.css\') }}'
    refresh = base.index(refresh_ref)
    assert responsive < refresh < base.index("</head>")
    assert base.count("/static/experience-refresh.css") == 1


def test_homepage_has_the_existing_sections_enhanced_by_the_refresh():
    home = HOME.read_text(encoding="utf-8")
    assert 'class="hero hero-phare"' in home
    assert 'class="stats stats-4"' in home
    assert 'class="derniers"' in home


def test_visual_refresh_changes_desktop_hierarchy_and_core_dashboard_surfaces():
    css = REFRESH.read_text(encoding="utf-8")
    required = (
        ".hero-phare {",
        "margin: -2.45rem .9rem 2rem;",
        ".stats.stats-4 {",
        ".tb-hero {",
        ".tb-acces-rapide-item:hover",
        ".tb-panneau",
        ".tb-sidebar-lien-actif",
        ".ai-hero,",
    )
    for selector_or_rule in required:
        assert selector_or_rule in css, selector_or_rule


def test_visual_refresh_respects_dark_theme_mobile_and_reduced_motion():
    css = REFRESH.read_text(encoding="utf-8")
    for required in (
        'html[data-theme="sombre"] .tb-hero',
        'html[data-theme="sombre"] .stat',
        "@media (max-width: 900px)",
        "@media (max-width: 600px)",
        "@media (prefers-reduced-motion: reduce)",
        "transition: none !important;",
    ):
        assert required in css, required


def test_visual_refresh_css_braces_are_balanced():
    css = REFRESH.read_text(encoding="utf-8")
    depth = 0
    for char in css:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "CSS contains an unmatched closing brace"
    assert depth == 0, "CSS contains an unmatched opening brace"
