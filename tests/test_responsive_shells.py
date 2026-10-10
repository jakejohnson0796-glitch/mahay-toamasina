from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
CSS = ROOT / "app" / "static" / "responsive-overrides.css"


def test_shell_responsive_layer_is_loaded_after_all_previous_layers_in_head():
    base = BASE.read_text(encoding="utf-8")
    responsive = base.index("/static/responsive.css")
    overrides = base.index("/static/responsive-overrides.css")
    assert responsive < overrides < base.index("</head>")
    for old_layer in ("responsive-foundation.css", "responsive-pages.css", "responsive-conversations.css", "responsive-shells.css"):
        assert f"/static/{old_layer}" not in base, old_layer


def test_admin_reference_tables_scroll_instead_of_being_clipped_on_mobile():
    css = CSS.read_text(encoding="utf-8")
    assert ".page-ops .table-manifeste" in css
    assert "overflow-x: auto !important;" in css
    assert "overscroll-behavior-x: contain;" in css
    assert ".page-ops .table-manifeste th," in css
    assert "white-space: nowrap;" in css


def test_auth_forms_keep_fields_and_actions_usable_on_narrow_screens():
    css = CSS.read_text(encoding="utf-8")
    for token in (
        ".page-auth .auth-form",
        "min-height: 44px;",
        ".page-auth .auth-password-toggle",
        "@media (max-width: 380px)",
        "white-space: normal;",
        "@media (orientation: landscape) and (max-height: 520px)",
    ):
        assert token in css, token


def test_public_help_contact_and_ops_shells_stay_within_viewport():
    css = CSS.read_text(encoding="utf-8")
    for token in (
        ".public-page",
        ".faq-page",
        ".mode-emploi-page",
        ".contact-page",
        ".ops-page",
        "max-width: 100%",
        "min-width: 0",
    ):
        assert token in css, token


def test_responsive_shell_layer_preserves_reduced_motion_preferences():
    css = CSS.read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "transition-duration: .01ms !important;" in css
