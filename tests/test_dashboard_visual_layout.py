"""Regression checks for dashboard progression-card layout."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
DASHBOARD = ROOT / "app" / "templates" / "dashboard_etudiant.html"
CSS = ROOT / "app" / "static" / "dashboard-polish.css"


def test_dashboard_layout_stylesheet_is_loaded_only_on_dashboard_after_global_overrides():
    base = BASE.read_text(encoding="utf-8")
    link = '/static/dashboard-polish.css?v={{ version_asset(\'dashboard-polish.css\') }}'
    assert base.count(link) == 1
    assert '{% if request.url.path == "/dashboard" %}' in base
    assert base.index("/static/responsive-overrides.css") < base.index(link) < base.index("</head>")
    assert base.index("/static/student-hub.css") < base.index(link)


def test_dashboard_progress_cards_override_the_shared_revision_grid_contract():
    css = CSS.read_text(encoding="utf-8")
    assert ".main-tb .tb-progression-dashboard .progression-carte" in css
    assert "display: block" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert "grid-template-columns: minmax(0, 1fr)" in css


def test_subject_names_and_percentages_keep_separate_flexible_columns():
    css = CSS.read_text(encoding="utf-8")
    assert ".progression-entete > div" in css
    assert "flex: 1 1 auto" in css
    assert ".progression-entete > b" in css
    assert "flex: 0 0 auto" in css
    assert "white-space: nowrap" in css
    assert "overflow-wrap: break-word" in css
    assert "word-break: normal" in css


def test_dashboard_progress_markup_and_score_data_are_unchanged():
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    assert 'class="tb-panneau tb-progression-dashboard"' in dashboard
    assert '<strong>{{ p.matiere }}</strong><span>{{ p.nb_quiz }} quiz</span>' in dashboard
    assert '<b>{{ p.moyenne }}%</b>' in dashboard
    assert 'style="width: {{ p.moyenne }}%"' in dashboard


def test_dashboard_progress_css_braces_are_balanced_and_motion_is_accessible():
    css = CSS.read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion: reduce)" in css
    depth = 0
    for char in css:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "CSS contains an unmatched closing brace"
    assert depth == 0, "CSS contains an unmatched opening brace"
