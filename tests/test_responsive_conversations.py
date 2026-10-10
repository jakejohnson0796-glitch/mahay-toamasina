from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
CSS = ROOT / "app" / "static" / "responsive-overrides.css"


def test_conversation_layer_is_loaded_after_all_other_responsive_styles():
    base = BASE.read_text(encoding="utf-8")
    responsive = base.index("/static/responsive.css")
    overrides = base.index("/static/responsive-overrides.css")
    head_end = base.index("</head>")
    assert responsive < overrides < head_end
    assert "/static/responsive-conversations.css" not in base


def test_mobile_circle_composer_has_ios_safe_font_and_comfortable_touch_targets():
    css = CSS.read_text(encoding="utf-8")
    assert ".contenu-clair .barre-composition #champ-message" in css
    assert "font-size: 16px !important;" in css
    assert "min-width: 2.75rem !important;" in css
    assert "min-height: 2.75rem !important;" in css
    assert ".contenu-clair .barre-composition .cercle-chat-outils" in css


def test_thread_panel_observes_safe_areas_and_mobile_navigation():
    css = CSS.read_text(encoding="utf-8")
    assert ".contenu-clair .panneau-thread" in css
    assert "env(safe-area-inset-top)" in css
    assert "env(safe-area-inset-bottom)" in css
    assert ".contenu-clair .bouton-fermer-thread" in css


def test_virtual_class_controls_remain_reachable_above_bottom_navigation():
    css = CSS.read_text(encoding="utf-8")
    assert ".page-classe .classe-salle-controls" in css
    assert "bottom: calc(4.25rem + env(safe-area-inset-bottom) + .35rem) !important;" in css
    assert "min-height: 2.75rem !important;" in css
    assert ".page-classe .classe-salle-stage" in css


def test_compact_landscape_uses_less_vertical_space_and_respects_reduced_motion():
    css = CSS.read_text(encoding="utf-8")
    assert "@media (orientation: landscape) and (max-height: 520px) and (max-width: 900px)" in css
    assert "height: clamp(9rem, calc(100dvh - 10.5rem), 23rem) !important;" in css
    assert "html body.cercle-mode-focus .contenu-clair .fenetre-chat" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
