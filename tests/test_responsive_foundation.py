from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
FOUNDATION = ROOT / "app" / "static" / "responsive-overrides.css"


def test_viewport_enables_ios_safe_area_layout():
    base = BASE.read_text(encoding="utf-8")
    assert 'name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"' in base


def test_all_page_stylesheets_are_loaded_before_the_single_global_responsive_layer():
    base = BASE.read_text(encoding="utf-8")
    override_ref = '/static/responsive-overrides.css?v={{ version_asset(\'responsive-overrides.css\') }}'
    assert override_ref in base
    override_pos = base.index(override_ref)
    head_end = base.index("</head>")
    assert override_pos < head_end

    for stylesheet in ("gamification.css", "onboarding.css", "activation.css", "responsive.css", "sidebar.css"):
        ref = f"/static/{stylesheet}"
        assert ref in base
        assert base.index(ref) < override_pos, stylesheet

    for old_layer in ("responsive-foundation.css", "responsive-pages.css", "responsive-conversations.css", "responsive-shells.css"):
        assert f"/static/{old_layer}" not in base, old_layer

    body = base[head_end:]
    for stylesheet in ("gamification.css", "onboarding.css", "activation.css", "responsive-overrides.css"):
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
