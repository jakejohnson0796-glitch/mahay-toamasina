"""Regression tests for virtual classroom layout and readability."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
DETAIL = ROOT / "app" / "templates" / "classe_detail.html"
CSS = ROOT / "app" / "static" / "classe.css"


def test_virtual_class_stylesheet_is_loaded_for_class_routes():
    base = BASE.read_text(encoding="utf-8")
    assert 'request.url.path.startswith("/classe")' in base
    assert '/static/classe.css?v={{ version_asset(\'classe.css\') }}' in base


def test_session_actions_use_a_separate_responsive_row_without_changing_routes():
    template = DETAIL.read_text(encoding="utf-8")
    sessions = template.split('aria-labelledby="seances-title"', 1)[1]
    assert '<div class="classe-row classe-row-seance">' in sessions
    for route in (
        '/classe/seances/{{ seance.id }}/demarrer',
        '/classe/seances/{{ seance.id }}/rejoindre',
        '/classe/seances/{{ seance.id }}/terminer',
        '/classe/seances/{{ seance.id }}/presences',
    ):
        assert route in sessions
    assert 'name="_csrf"' in sessions


def test_session_titles_cannot_break_into_one_letter_per_line():
    css = CSS.read_text(encoding="utf-8")
    assert ".classe-row-seance .classe-row-main strong" in css
    assert "word-break: normal" in css
    assert "overflow-wrap: break-word" in css
    assert ".classe-row-seance .classe-row-actions" in css
    assert "grid-template-columns: repeat(auto-fit, minmax(min(100%, 8rem), 1fr))" in css


def test_virtual_class_styles_remain_responsive_and_css_braces_are_balanced():
    css = CSS.read_text(encoding="utf-8")
    assert "@media (max-width: 560px)" in css
    assert "@media (max-width: 820px)" in css
    depth = 0
    for char in css:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "CSS contains an unmatched closing brace"
    assert depth == 0, "CSS contains an unmatched opening brace"
