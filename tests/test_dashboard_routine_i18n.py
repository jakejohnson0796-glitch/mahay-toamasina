from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANGUAGE_SCRIPT = ROOT / "app" / "static" / "js" / "langue.js"


def test_daily_routine_labels_are_translated_in_malagasy_and_english():
    script = LANGUAGE_SCRIPT.read_text(encoding="utf-8")
    mg = script.split("var TRADUCTIONS_MG = Object.freeze({", 1)[1].split(
        "var TRADUCTIONS_EN = Object.freeze({", 1
    )[0]
    en = script.split("var TRADUCTIONS_EN = Object.freeze({", 1)[1].split(
        "var noeudsOriginaux =", 1
    )[0]

    labels = (
        '"Ta routine du jour":',
        '"Une petite session régulière vaut mieux qu\'une longue session rare.":',
        '"Progression de la routine du jour":',
        '"Un mini-quiz":',
        '"Une ressource de cours":',
        '"Un échange utile":',
        '"Routine terminée aujourd’hui. Bravo pour ta régularité !":',
    )
    for label in labels:
        assert label in mg, f"Traduction malagasy manquante : {label}"
        assert label in en, f"Traduction anglaise manquante : {label}"
