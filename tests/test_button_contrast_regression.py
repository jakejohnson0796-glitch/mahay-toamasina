"""Regressions for readable primary actions in light and dark themes."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DESIGN_CSS = ROOT / "app" / "static" / "global-design-system.css"
BASE_TEMPLATE = ROOT / "app" / "templates" / "base.html"
QUIZ_TEMPLATE = ROOT / "app" / "templates" / "quiz_config.html"


def _block(css: str, selector: str) -> str:
    match = re.search(
        rf"(?m)^{re.escape(selector)}\s*\{{([^{{}}]*)\}}",
        css,
    )
    assert match, f"CSS block not found: {selector}"
    return match.group(1)


def _variables(css: str, selector: str) -> dict[str, str]:
    block = _block(css, selector)
    return dict(
        re.findall(r"(--[a-zA-Z0-9_-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;", block)
    )


def _rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    assert len(value) == 6, f"Expected a hex color, got {value!r}"
    return tuple(int(value[index : index + 2], 16) / 255 for index in (0, 2, 4))


def _luminance(value: str) -> float:
    channels = []
    for channel in _rgb(value):
        channels.append(
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
        )
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(foreground: str, background: str) -> float:
    first, second = _luminance(foreground), _luminance(background)
    return (max(first, second) + 0.05) / (min(first, second) + 0.05)


def test_primary_button_text_meets_wcag_aa_in_both_themes() -> None:
    css = DESIGN_CSS.read_text(encoding="utf-8")
    themes = (
        (":root", "thème clair"),
        ('html[data-theme="sombre"]', "thème sombre"),
    )

    for selector, label in themes:
        values = _variables(css, selector)
        foreground = values["--primary-contrast"]
        for background_name in ("--primary", "--primary-hover"):
            ratio = _contrast(foreground, values[background_name])
            assert ratio >= 4.5, (
                f"Contraste insuffisant en {label} pour {background_name}: "
                f"{ratio:.2f}:1 (minimum 4.5:1)"
            )


def test_primary_button_overrides_legacy_background_and_text_conflict() -> None:
    css = DESIGN_CSS.read_text(encoding="utf-8")
    primary_rules = re.findall(
        r"(?m)^\.bouton-primaire\s*\{([^{}]*)\}", css
    )
    hover_rules = re.findall(
        r"(?m)^\.bouton-primaire:hover\s*\{([^{}]*)\}", css
    )
    assert primary_rules and hover_rules

    # The last declarations must win over the legacy !important background.
    assert "background: var(--primary) !important;" in primary_rules[-1]
    assert "border-color: var(--primary) !important;" in primary_rules[-1]
    assert "color: var(--primary-contrast) !important;" in primary_rules[-1]
    assert (
        "-webkit-text-fill-color: var(--primary-contrast) !important;"
        in primary_rules[-1]
    )
    assert "background: var(--primary-hover) !important;" in hover_rules[-1]
    assert "color: var(--primary-contrast) !important;" in hover_rules[-1]

    disabled_rule = re.search(
        r"(?s)\.bouton-primaire:disabled,\s*"
        r"\.bouton-primaire:disabled:hover\s*\{([^{}]*)\}",
        css,
    )
    assert disabled_rule
    assert "opacity: 1;" in disabled_rule.group(1)
    assert "color: var(--primary-contrast) !important;" in disabled_rule.group(1)


def test_global_design_system_is_loaded_after_legacy_refonte_css() -> None:
    base = BASE_TEMPLATE.read_text(encoding="utf-8")
    assert base.index("/static/refonte.css") < base.index(
        "/static/global-design-system.css"
    )


def test_quiz_generation_button_uses_the_accessible_primary_variant() -> None:
    template = QUIZ_TEMPLATE.read_text(encoding="utf-8")
    assert 'class="bouton bouton-primaire" type="submit" data-ai-submit>Générer mon quiz</button>' in template
