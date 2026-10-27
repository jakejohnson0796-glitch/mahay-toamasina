"""Regression checks for the global language selector placement and accessibility."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
SIDEBAR_CSS = ROOT / "app" / "static" / "sidebar.css"
LANGUAGE_JS = ROOT / "app" / "static" / "js" / "langue.js"


def test_language_selector_is_global_singleton_at_sidebar_preferences_end():
    base = BASE.read_text(encoding="utf-8")
    assert base.count('id="select-langue"') == 1
    assert base.index("<nav class=\"tb-sidebar-nav\"") < base.index('id="select-langue"') < base.index("</aside>")
    assert "tb-sidebar-langue-entete" in base
    assert 'for="select-langue" data-langue-label' in base
    assert '<option value="fr">Français</option>' in base
    assert '<option value="mg">Malagasy</option>' in base
    assert '<option value="en">English</option>' in base
    assert 'FR · MG · EN' in base
    brand_end = base.index("</div>", base.index('<div class="tb-sidebar-marque">'))
    assert base.index('id="select-langue"') > brand_end


def test_language_selector_keeps_the_existing_translation_script_contract():
    base = BASE.read_text(encoding="utf-8")
    script = LANGUAGE_JS.read_text(encoding="utf-8")
    assert "/static/js/langue.js?v={{ version_asset('js/langue.js') }}" in base
    assert 'var SELECTEUR = "#select-langue";' in script
    assert 'var TRADUCTIONS_EN = Object.freeze({' in script
    assert 'if (langue === "en") return traduireChaineAnglaise(source);' in script
    assert 'return langue === "mg" || langue === "en" ? langue : "fr";' in script
    assert 'selecteur.addEventListener("change"' in script
    assert "localStorage.setItem(CLE_LANGUE, langueActuelle)" in script


def test_language_selector_has_keyboard_focus_and_compact_sidebar_styles():
    css = SIDEBAR_CSS.read_text(encoding="utf-8")
    assert ".tb-sidebar-langue select:focus-visible" in css
    assert "body.sidebar-compact .tb-sidebar-langue" in css
    assert "@media (max-width: 900px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    depth = 0
    for char in css:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "CSS contains an unmatched closing brace"
    assert depth == 0, "CSS contains an unmatched opening brace"


def test_english_dictionary_covers_core_ui_and_preserves_scientific_content():
    import re

    script = LANGUAGE_JS.read_text(encoding="utf-8")
    english = script.split("var TRADUCTIONS_EN = Object.freeze({", 1)[1].split("\n  });", 1)[0]
    keys = re.findall(r'^\s*"((?:\\.|[^"\\])*)"\s*:', english, re.MULTILINE)

    assert len(keys) >= 600
    assert len(keys) == len(set(keys)), "English dictionary contains duplicate keys"
    for source, translated in {
        '"Tableau de bord"': '"Dashboard"',
        '"Tuteur IA"': '"AI Tutor"',
        '"Lancer le quiz"': '"Start quiz"',
        '"Mes cercles"': '"My study circles"',
        '"Sécurité du compte"': '"Account security"',
        '"Salle de classe"': '"Classroom"',
        '"Vérification facultative du résumé IA"': '"Optional AI summary review"',
    }.items():
        assert source + ": " + translated in english

    assert '"[data-rendu]"' in script
    assert '".katex"' in script
    assert '"[data-no-translate]"' in script
    assert 'if (langue === "en") return traduireChaineAnglaise(source);' in script


def test_learning_check_in_has_complete_english_texts():
    import re

    script = (ROOT / "app" / "static" / "js" / "bilan-reprise.js").read_text(encoding="utf-8")
    french = script.split("    fr: {", 1)[1].split("    mg: {", 1)[0]
    english = script.split("    en: {", 1)[1].split("\n  };", 1)[0]
    french_keys = set(re.findall(r'^      ([A-Za-z][A-Za-z0-9_]*):', french, re.MULTILINE))
    english_keys = set(re.findall(r'^      ([A-Za-z][A-Za-z0-9_]*):', english, re.MULTILINE))

    assert french_keys - english_keys == set()
    assert 'savedLanguage === "mg" || savedLanguage === "en"' in script
    for key in ("comprendre", "pratiquer", "verifier", "terminee"):
        assert key + ":" in english
    assert 'return value == null ? key : value;' in script


def test_language_selector_is_visible_in_mobile_header_and_synchronizes():
    base = BASE.read_text(encoding="utf-8")
    css = (ROOT / "app" / "static" / "interface-polish.css").read_text(encoding="utf-8")
    script = LANGUAGE_JS.read_text(encoding="utf-8")
    smoke = (ROOT / "scripts" / "smoke_language_switcher.mjs").read_text(encoding="utf-8")

    mobile_header = base.split('<header class="mobile-entete-app"', 1)[1].split("</header>", 1)[0]
    assert 'id="select-langue-mobile"' in mobile_header
    assert 'class="selecteur-langue-mobile"' in mobile_header
    assert '<option value="en">English</option>' in mobile_header
    assert ".mobile-entete-app .selecteur-langue-mobile" in css
    assert "@media (max-width: 768px)" in css
    assert 'var SELECTEUR = "#select-langue, #select-langue-mobile";' in script
    assert 'document.querySelectorAll(SELECTEUR).forEach' in script
    assert "mobile_selector_sync: true" in smoke


def test_english_fragment_fallback_and_pwa_cache_refresh_are_present():
    script = LANGUAGE_JS.read_text(encoding="utf-8")
    smoke = (ROOT / "scripts" / "smoke_language_switcher.mjs").read_text(encoding="utf-8")
    service_worker = (ROOT / "app" / "static" / "sw.js").read_text(encoding="utf-8")

    assert "function traduireFragmentsAnglais(source)" in script
    assert "RE_TRADUCTIONS_EN_FRAGMENTS" in script
    assert "texte.length > 900" in script
    assert 'fallbackEnglish.textContent !== \'Search for a document in approved documents\'' in smoke
    assert "locales: ['fr', 'mg', 'en']" in smoke
    assert 'const CACHE_NOM = "mahay-static-v3";' in service_worker

