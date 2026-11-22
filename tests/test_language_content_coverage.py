"""Coverage checks for the expanded English and Malagasy interface dictionaries."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANGUAGE_JS = ROOT / "app" / "static" / "js" / "langue.js"
SMOKE = ROOT / "scripts" / "smoke_language_switcher.mjs"
STUDENT_DASHBOARD = ROOT / "app" / "templates" / "dashboard_etudiant.html"


def _dictionary(source: str, start_marker: str, end_marker: str) -> dict[str, str]:
    start = source.index(start_marker) + len(start_marker)
    end = source.index(end_marker, start)
    section = source[start:end]
    pairs = re.findall(
        r'^\s*("(?:\\.|[^"\\])*")\s*:\s*("(?:\\.|[^"\\])*")\s*,?\s*$',
        section,
        re.MULTILINE,
    )
    return {json.loads(key): json.loads(value) for key, value in pairs}


def test_teacher_help_legal_and_library_pages_have_english_and_malagasy_copy():
    source = LANGUAGE_JS.read_text(encoding="utf-8")
    malagasy = _dictionary(
        source,
        "var TRADUCTIONS_MG = Object.freeze({",
        "var TRADUCTIONS_EN",
    )
    english = _dictionary(
        source,
        "var TRADUCTIONS_EN = Object.freeze({",
        "var noeudsOriginaux",
    )

    assert malagasy["Prépare tes cours, accompagne tes apprenants et organise tes séances depuis un espace pensé pour l’enseignement."] == (
        "Omano ny lesonao, araho ny mpianatrao ary alamino ny fotoam-pianarana ao amin'ny sehatra natao ho an'ny fampianarana."
    )
    assert english["Prépare tes cours, accompagne tes apprenants et organise tes séances depuis un espace pensé pour l’enseignement."] == (
        "Prepare lessons, support your learners, and organise sessions in a workspace designed for teaching."
    )
    assert malagasy["Centre d'aide · MITARIDALA"] == "Ivon-toerana fanampiana · MITARIDALA"
    assert english["Centre d'aide · MITARIDALA"] == "MITARIDALA Help Centre"
    assert malagasy["Éthique, conditions d’utilisation et confidentialité"] == (
        "Fitsipi-pitondrantena, fepetra fampiasana ary tsiambaratelo"
    )
    assert english["Éthique, conditions d’utilisation et confidentialité"] == (
        "Ethics, terms of use, and privacy"
    )
    assert english["Demande reçue"] == "Request received"
    assert malagasy["Alertes d'harmonisation des cours"] == (
        "Fampandrenesana momba ny fandrindrana ny lesona"
    )
    assert english["Alertes d'harmonisation des cours"] == "Course harmonisation alerts"
    assert malagasy["Rechercher dans la bibliothèque"] == "Hitady ao amin'ny tahiry"
    assert english["Rechercher dans la bibliothèque"] == "Search the library"
    assert malagasy["Bienvenue à nouveau."] == "Tongasoa indray."
    assert english["Bienvenue à nouveau."] == "Welcome back."
    assert malagasy["Création de compte"] == "Famoronana kaonty"
    assert english["Création de compte"] == "Create an account"
    assert malagasy["Priorité du jour"] == "Laharam-pahamehana androany"
    assert english["Priorité du jour"] == "Today's priority"


def test_personalised_teacher_greetings_are_translated_without_losing_the_name():
    source = LANGUAGE_JS.read_text(encoding="utf-8")
    assert r"cle.match(/^Bonjour\s+(.+?)\s*[.!]$/i)" in source
    assert 'return "Hello, " + match[1].trim() + ".";' in source
    assert 'return "Manao ahoana, " + match[1].trim() + ".";' in source
    assert r'\\n    if (match)' not in source


def test_language_smoke_covers_both_locales_and_protects_existing_content():
    smoke = SMOKE.read_text(encoding="utf-8")
    assert "Teacher workspace introduction was not translated to English" in smoke
    assert "Teacher workspace introduction was not translated to Malagasy" in smoke
    assert "Help centre heading was not translated to English" in smoke
    assert "Legal page heading was not translated to Malagasy" in smoke
    assert "Personalised greeting was not translated to English" in smoke
    assert "ai scientific content was modified" in smoke.lower()


def test_student_dashboard_copy_uses_consistent_accents():
    dashboard = STUDENT_DASHBOARD.read_text(encoding="utf-8")
    assert "Prêt à continuer ton apprentissage ?" in dashboard
    assert "pour ta filière." in dashboard
    assert "Votre accès Premium n'est plus actif." in dashboard
    assert "Dernière consultation :" in dashboard
    assert "Activité récente" in dashboard
    assert "Mes cercles d’étude" in dashboard
    assert "Échéances à venir" in dashboard
