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
