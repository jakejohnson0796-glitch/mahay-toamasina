from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
FOUNDATION = ROOT / "app" / "static" / "responsive-foundation.css"


def test_viewport_enables_ios_safe_area_layout():
    base = BASE.read_text(encoding="utf-8")
    assert 'name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"' in base


def test_all_page_stylesheets_are_loaded_before_the_global_responsive_layer():
    base = BASE.read_text(encoding="utf-8")
    foundation_ref = '/static/responsive-foundation.css?v={{ version_asset(\'responsive-foundation.css\') }}'
    assert foundation_ref in base
    foundation_pos = base.index(foundation_ref)
    head_end = base.index("</head>")
    assert foundation_pos < head_end

    for stylesheet in ("gamification.css", "onboarding.css", "activation.css", "responsive.css"):
        ref = f"/static/{stylesheet}"
        assert ref in base
        assert base.index(ref) < foundation_pos, stylesheet

    body = base[head_end:]
    for stylesheet in ("gamification.css", "onboarding.css", "activation.css"):
        assert f"/static/{stylesheet}" not in body, stylesheet


def test_responsive_foundation_keeps_mobile_navigation_legible_and_touch_friendly():
    css = FOUNDATION.read_text(encoding="utf-8")
    required = (
        "grid-template-columns: repeat(6, minmax(0, 1fr)) !important;",
        "min-height: 2.9rem !important;",
        "font-size: clamp(.5rem, 2.3vw, .66rem) !important;",
        "white-space: normal !important;",
        "display: inline-grid !important;",
        "env(safe-area-inset-bottom)",
        "@media (max-width: 340px)",
        "@media (orientation: landscape) and (max-height: 520px)",
        "@media (pointer: coarse)",
        "min-height: max(var(--gm-touch-target), 44px);",
        "@media (prefers-reduced-motion: reduce)",
    )
    for token in required:
        assert token in css, token


def test_responsive_foundation_preserves_flexible_layout_primitives():
    css = FOUNDATION.read_text(encoding="utf-8")
    required = (
        "--gm-layout-gutter: clamp(",
        "min-width: 0;",
        "max-width: 100%",
        "overscroll-behavior: contain;",
        "overflow-x: auto;",
        "outline-offset: 2px;",
    )
    for token in required:
        assert token in css, token
