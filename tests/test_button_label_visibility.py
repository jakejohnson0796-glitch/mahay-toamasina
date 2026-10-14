"""Regression checks for button label visibility and accessible naming."""
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app" / "static" / "style.css").read_text(encoding="utf-8")
BASE = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")


def _css_rule(selector: str) -> str:
    match = re.search(
        rf"(?m)^{re.escape(selector)}\s*\{{([^}}]*)\}}",
        CSS,
        flags=re.DOTALL,
    )
    assert match, f"CSS rule not found: {selector}"
    return match.group(1)


def test_button_default_foreground_uses_theme_text_token():
    rule = _css_rule("button")
    assert "color: var(--content-text, currentColor);" in rule


def test_disabled_buttons_do_not_fade_their_labels():
    rule = _css_rule("button:disabled")
    assert re.search(r"opacity:\s*1(?:\.0+)?\s*;", rule)

    primary_disabled = re.search(
        r"(?m)^\.bouton-primaire:disabled,\s*"
        r"\.bouton-primaire:disabled:hover\s*\{([^}]*)\}",
        CSS,
    )
    assert primary_disabled, "Disabled primary button rule not found"
    assert "opacity: 1;" in primary_disabled.group(1)
    assert "color: var(--content-surface);" in primary_disabled.group(1)


def test_active_toolbar_control_has_theme_safe_foreground():
    rule = _css_rule(".bouton-controle-actif")
    assert "color: var(--content-surface);" in rule


def test_account_menu_has_accessible_name_and_fallback_label():
    marker = 'class="tb-sidebar-compte"'
    class_index = BASE.index(marker)
    start = BASE.rfind("<button", 0, class_index)
    end = BASE.index("</button>", class_index) + len("</button>")
    button = BASE[start:end]

    assert 'aria-label="Ouvrir le menu du compte"' in button
    assert "{% else %}" in button
    assert 'class="tb-sidebar-compte-nom">Mon compte' in button
