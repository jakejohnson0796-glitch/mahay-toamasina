import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
UNIVERSAL = ROOT / "app" / "static" / "responsive-universal.css"
MANIFEST = ROOT / "app" / "static" / "manifest.json"


def test_viewport_keeps_zoom_available_and_resizes_for_mobile_keyboard():
    base = BASE.read_text(encoding="utf-8")
    viewport = re.search(r'<meta name="viewport" content="([^"]+)"', base)
    assert viewport, "La balise viewport doit exister."
    content = viewport.group(1)
    assert "width=device-width" in content
    assert "initial-scale=1.0" in content
    assert "viewport-fit=cover" in content
    assert "interactive-widget=resizes-content" in content
    assert "user-scalable=no" not in content
    assert "maximum-scale=1" not in content


def test_ios_home_screen_metadata_and_android_manifest_are_present():
    base = BASE.read_text(encoding="utf-8")
    for token in (
        'rel="apple-touch-icon"',
        'name="apple-mobile-web-app-capable" content="yes"',
        'name="apple-mobile-web-app-status-bar-style" content="black-translucent"',
        'name="apple-mobile-web-app-title" content="MITARIDALA"',
        'name="mobile-web-app-capable" content="yes"',
    ):
        assert token in base, token

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["display"] in ("standalone", "minimal-ui")
    assert manifest["name"]
    assert manifest["short_name"]
    assert manifest["theme_color"].upper() == "#0D4645"
    assert any(icon.get("purpose") == "maskable" for icon in manifest["icons"])


def test_universal_responsive_layer_is_loaded_after_all_page_styles():
    base = BASE.read_text(encoding="utf-8")
    head = base.split("</head>", 1)[0]
    styles = re.findall(r'<link[^>]+href="/static/([^"?]+\.css)(?:\?[^"]*)?"', head)
    assert styles, "Aucune feuille de style applicative trouvée."
    assert styles[-1] == "responsive-universal.css"
    assert styles.count("responsive-universal.css") == 1


def test_mobile_inputs_and_primary_controls_support_touch_and_ios_zoom_rules():
    css = UNIVERSAL.read_text(encoding="utf-8")
    assert "--gm-touch-target: 44px;" in css
    assert "min-height: var(--gm-touch-target);" in css
    assert "min-width: var(--gm-touch-target);" in css
    assert "font-size: 16px !important;" in css
    assert "@media (hover: none) and (pointer: coarse)" in css
    assert "@media (max-width: 300px)" in css
    assert "env(safe-area-inset-top" in css
    assert "env(safe-area-inset-bottom" in css


def test_layout_supports_landscape_reduced_motion_and_high_contrast():
    css = UNIVERSAL.read_text(encoding="utf-8")
    assert "@media (orientation: landscape)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "@media (prefers-contrast: more)" in css
    assert "@media (forced-colors: active)" in css
