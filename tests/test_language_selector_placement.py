"""Regression checks for language preferences, translation coverage and protected content."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
SECURITY = ROOT / "app" / "templates" / "securite.html"
SIDEBAR_CSS = ROOT / "app" / "static" / "sidebar.css"
INTERFACE_CSS = ROOT / "app" / "static" / "interface-polish.css"
LANGUAGE_JS = ROOT / "app" / "static" / "js" / "langue.js"
SMOKE = ROOT / "scripts" / "smoke_language_switcher.mjs"


def test_language_selector_lives_only_in_account_settings():
    base = BASE.read_text(encoding="utf-8")
    settings = SECURITY.read_text(encoding="utf-8")
    assert "select-langue" not in base
    assert settings.count('id="select-langue-parametres"') == 1
    assert 'class="ops-security-card ops-language-settings" id="language-settings"' in settings
    assert 'for="select-langue-parametres"' in settings
    assert '<option value="fr" data-no-translate>Français</option>' in settings
    assert '<option value="mg" data-no-translate>Malagasy</option>' in settings
    assert '<option value="en" data-no-translate>English</option>' in settings
    assert "mémorisé dans ce navigateur" in settings
    assert "select-langue-mobile" not in base


def test_language_selector_uses_global_translation_engine_and_persists_choice():
    base = BASE.read_text(encoding="utf-8")
    settings = SECURITY.read_text(encoding="utf-8")
    script = LANGUAGE_JS.read_text(encoding="utf-8")
    assert "/static/js/langue.js?v={{ version_asset('js/langue.js') }}" in base
    assert 'var SELECTEUR = "#select-langue-parametres";' in script
    assert 'var TRADUCTIONS_EN = Object.freeze({' in script
    assert 'if (langue === "en") return traduireChaineAnglaise(source);' in script
    assert 'return langue === "mg" || langue === "en" ? langue : "fr";' in script
    assert 'selecteur.addEventListener("change"' in script
    assert "localStorage.setItem(CLE_LANGUE, langueActuelle)" in script
    assert "data-selecteur-langue" in settings


def test_language_preference_card_is_responsive_and_keyboard_accessible():
    css = INTERFACE_CSS.read_text(encoding="utf-8")
    sidebar_css = SIDEBAR_CSS.read_text(encoding="utf-8")
    assert ".ops-language-settings" in css
    assert ".ops-language-settings select:focus-visible" in css
    assert "@media (max-width: 640px)" in css
    assert "var(--content-surface)" in css
    assert "var(--content-text)" in css
    assert ".tb-sidebar-langue" not in sidebar_css
    depth = 0
    for char in css:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "CSS contains an unmatched closing brace"
    assert depth == 0, "CSS contains an unmatched opening brace"


def test_english_dictionary_covers_core_ui_and_preserves_scientific_content():
    script = LANGUAGE_JS.read_text(encoding="utf-8")
    english = script.split("var TRADUCTIONS_EN = Object.freeze({", 1)[1].split("\n  });", 1)[0]
    keys = re.findall(r'^\s*"((?:\\.|[^"\\])*)"\s*:', english, re.MULTILINE)
    assert len(keys) >= 1_600
    assert len(keys) == len(set(keys)), "English dictionary contains duplicate keys"
    for source, translated in {
        "Tableau de bord": "Dashboard",
        "Tuteur IA": "AI Tutor",
        "Lancer le quiz": "Start quiz",
        "Mes cercles": "My study circles",
        "Sécurité du compte": "Account security",
        "Salle de classe": "Classroom",
        "Vérification facultative du résumé IA": "Optional AI summary review",
        "Langue de l’interface": "Interface language",
        "Langue préférée": "Preferred language",
        "Ton identité": "Your identity",
        "Régénérer les codes de secours": "Regenerate backup codes",
        "Rechercher dans les notifications": "Search notifications",
        "Les jeux classiques": "Classic games",
        "Ne reste pas bloqué sur une notion.": "Don't get stuck on a topic.",
        "Centre de notifications": "Notification center",
        "Guide officiel · MITARIDALA": "Official guide · MITARIDALA",
    }.items():
        assert f'"{source}": "{translated}"' in english, f"Missing or incorrect English translation for: {source}"
    assert '"[data-rendu]"' in script
    assert '".katex"' in script
    assert '"[data-no-translate]"' in script
    assert 'if (langue === "en") return traduireChaineAnglaise(source);' in script


def test_malagasy_dictionary_covers_settings_circles_and_games():
    script = LANGUAGE_JS.read_text(encoding="utf-8")
    malagasy = script.split("var TRADUCTIONS_MG = Object.freeze({", 1)[1].split("\n  });", 1)[0]
    keys = re.findall(r'^\s*"((?:\\.|[^"\\])*)"\s*:', malagasy, re.MULTILINE)
    assert len(keys) >= 3_000
    assert len(keys) == len(set(keys)), "Malagasy dictionary contains duplicate keys"
    for source, translated in {
        "Langue de l’interface": "Fitenin'ny interface",
        "Langue préférée": "Fiteny tiana hampiasaina",
        "Les jeux classiques": "Ny lalao mahazatra",
        "À l’échelle de Madagascar · Cercles d’étude": "Manerana an'i Madagasikara · Faribolana fianarana",
        "Apprendre en jouant": "Mianatra amin'ny alalan'ny lalao",
        "Choisir mon université": "Safidio ny oniversiteko",
        "Revenir à mon tableau de bord": "Hiverina amin'ny tabilao fandraisana",
    }.items():
        assert f'"{source}": "{translated}"' in malagasy, f"Missing or incorrect Malagasy translation for: {source}"
    smoke = SMOKE.read_text(encoding="utf-8")
    assert "The settings heading was not translated to Malagasy" in smoke
    assert "The study circles heading was not translated to Malagasy" in smoke
    assert "The long about-page introduction was not translated to Malagasy" in smoke


def test_learning_check_in_has_complete_english_texts():
    script = (ROOT / "app" / "static" / "js" / "bilan-reprise.js").read_text(encoding="utf-8")
    french = script.split("    fr: {", 1)[1].split("    mg: {", 1)[0]
    english = script.split("    en: {", 1)[1].split("\n  };", 1)[0]
    french_keys = set(re.findall(r'^      ([A-Za-z][A-Za-z0-9_]*):', french, re.MULTILINE))
    english_keys = set(re.findall(r'^      ([A-Za-z][A-Za-z0-9_]*):', english, re.MULTILINE))
    assert french_keys - english_keys == set()
    assert 'savedLanguage === "mg" || savedLanguage === "en"' in script
    for key in ("comprendre", "pratiquer", "verifier", "terminee"):
        assert key + ":" in english
    assert "return value == null ? key : value;" in script


def test_language_smoke_exercises_settings_selection_and_translation_fallback():
    script = LANGUAGE_JS.read_text(encoding="utf-8")
    smoke = SMOKE.read_text(encoding="utf-8")
    service_worker = (ROOT / "app" / "static" / "sw.js").read_text(encoding="utf-8")
    assert "function traduireFragmentsAnglais(source)" in script
    assert "RE_TRADUCTIONS_EN_FRAGMENTS" in script
    assert "texte.length > 900" in script
    assert "select-langue-parametres" in smoke
    assert "select-langue-mobile" not in smoke
    assert "fallbackEnglish.textContent !== 'Search for a document in approved documents'" in smoke
    assert "locales: ['fr', 'mg', 'en']" in smoke
    assert 'const CACHE_NOM = "mahay-static-v4";' in service_worker
