"""Regression checks for global, accessible site micro-animations."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
MOTION = ROOT / "app" / "static" / "motion-polish.css"


def test_global_motion_layer_is_loaded_once_after_existing_styles():
    base = BASE.read_text(encoding="utf-8")
    link = '/static/motion-polish.css?v={{ version_asset(\'motion-polish.css\') }}'
    assert base.count(link) == 1
    assert base.index("/static/experience-refresh.css") < base.index(link) < base.index("</head>")


def test_motion_layer_adds_page_entry_notice_and_button_feedback():
    css = MOTION.read_text(encoding="utf-8")
    for token in (
        "@keyframes gm-page-fade-in",
        "@keyframes gm-notice-arrive",
        ".app-page > main[data-page]",
        ".app-page main .bouton:active:not(:disabled)",
        ".tb-sidebar-lien:hover .tb-icone",
        "focus-visible",
    ):
        assert token in css, token


def test_motion_layer_respects_reduced_motion_and_does_not_transform_main():
    css = MOTION.read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion: no-preference)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    main_rule = css.split(".app-page > main[data-page] {", 1)[1].split("}", 1)[0]
    assert "animation: gm-page-fade-in" in main_rule
    assert "transform:" not in main_rule


def test_motion_css_is_balanced_and_contains_no_infinite_animation():
    css = MOTION.read_text(encoding="utf-8")
    depth = 0
    for char in css:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "CSS contains an unmatched closing brace"
    assert depth == 0, "CSS contains an unmatched opening brace"
    assert "infinite" not in css
