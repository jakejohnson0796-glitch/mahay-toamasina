from pathlib import Path
from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = [
    "admin_index.html",
    "admin_abonnements.html",
    "admin_sponsors.html",
    "admin_stats.html",
    "admin_utilisateurs.html",
    "abonnement.html",
    "sponsoring.html",
    "securite.html",
    "configurer_2fa.html",
]


def test_ops_templates_compile():
    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"))
    for name in TEMPLATES:
        assert env.get_template(name) is not None


def test_ops_templates_have_no_inline_style():
    for name in TEMPLATES:
        content = (ROOT / "app" / "templates" / name).read_text(encoding="utf-8")
        assert ' style="' not in content, name


def test_ops_css_is_loaded_on_expected_pages():
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    assert 'version_asset(\'ops.css\')' in base
    assert "page-ops" in base


def test_ops_css_has_responsive_rules_and_core_surfaces():
    css = (ROOT / "app" / "static" / "ops.css").read_text(encoding="utf-8")
    for selector in (".ops-hero", ".ops-table", ".ops-profile", ".ops-offer", ".ops-admin-groups", "@media(max-width:740px)"):
        assert selector in css

def test_mfa_setup_is_guided_accessible_and_responsive():
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    setup = (ROOT / "app" / "templates" / "configurer_2fa.html").read_text(encoding="utf-8")
    css = (ROOT / "app" / "static" / "mfa.css").read_text(encoding="utf-8")
    script = (ROOT / "app" / "static" / "js" / "mfa-setup.js").read_text(encoding="utf-8")
    security = (ROOT / "app" / "templates" / "securite.html").read_text(encoding="utf-8")

    assert 'request.url.path.startswith("/securite")' in base
    assert "version_asset('mfa.css')" in base
    assert "mfa-setup.js" in base
    assert "mfa-step-number" in setup
    assert "data-copy-secret" in setup
    assert "data-mfa-code-form novalidate" in setup
    assert "data-mfa-validation-message" in setup
    assert 'style="' not in setup
    assert "data-mfa-validation-message" in script
    assert "prefers-reduced-motion: reduce" in css
    assert "@media (max-width: 560px)" in css
    assert css.count("{") == css.count("}")
    assert "utilisateur.totp_active or utilisateur.email_otp_active" in security
    assert "</script\\n" not in security

