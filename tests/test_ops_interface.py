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
