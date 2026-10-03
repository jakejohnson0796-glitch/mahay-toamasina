from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
RESPONSIVE = ROOT / "app" / "static" / "responsive.css"


def test_base_loads_responsive_css_after_existing_styles():
    base = BASE.read_text(encoding="utf-8")
    marker = '/static/responsive.css?v={{ version_asset(\'responsive.css\') }}'
    assert marker in base
    assert base.index(marker) > base.index('/static/sidebar.css')


def test_responsive_contract_is_fluid_and_safe():
    css = RESPONSIVE.read_text(encoding="utf-8")
    required = [
        "--gm-page-gutter: clamp(",
        "100dvh",
        "100vw",
        "min-width: 0",
        "max-width: 100%",
        "text-size-adjust: 100%",
        "@media (max-width: 390px)",
        "@media (max-width: 340px)",
        "@media (orientation: landscape) and (max-height: 520px)",
        "@media (prefers-reduced-motion: reduce)",
    ]
    for token in required:
        assert token in css, token


def test_ultra_small_circle_overrides_neutralize_inline_mobile_heights():
    css = RESPONSIVE.read_text(encoding="utf-8")
    required = [
        ".cercles-hero-visuel {",
        "min-height: 0 !important;",
        "height: auto !important;",
        ".cercles-hero-contenu {",
        "max-width: none !important;",
        ".cercles-hero-titre {",
        "font-size: clamp(1.45rem, 7.6vw, 2rem) !important;",
        "@media (max-width: 300px)",
    ]
    for token in required:
        assert token in css, token


def test_mobile_emoji_picker_is_compact():
    css = RESPONSIVE.read_text(encoding="utf-8")
    required = [
        ".contenu-clair .panneau-emojis-v2 {",
        "max-height: min(255px, calc(100dvh - 92px)) !important;",
        "width: min(300px, calc(100vw - 16px)) !important;",
        "max-height: min(225px, calc(100dvh - 88px)) !important;",
        "max-height: min(205px, calc(100dvh - 82px)) !important;",
        ".contenu-clair .grille-emojis-v2 {",
        "max-height: 118px !important;",
    ]
    for token in required:
        assert token in css, token
