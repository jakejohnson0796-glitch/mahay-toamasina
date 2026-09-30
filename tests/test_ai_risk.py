from app.ai_risk import (
    STRATEGIE_LEGERE,
    STRATEGIE_RENFORCEE,
    STRATEGIE_STANDARD,
    analyser_risque,
)


def _question():
    return {
        "question": "Quelle est la définition de base ?",
        "choix": ["A", "B", "C"],
        "index_bonne_reponse": 0,
        "explication": "A.",
        "notion": "Base",
    }


def test_quiz_simple_utilise_une_verification_legere():
    result = analyser_risque(
        [_question()] * 5,
        matiere="Histoire",
        niveau="L1",
        difficulte="Facile",
        signaux_recurrents=0,
    )
    assert result["strategie"] == STRATEGIE_LEGERE
    assert result["score"] <= 1


def test_quiz_intermediaire_utilise_la_verification_standard():
    result = analyser_risque(
        [_question()] * 10,
        matiere="Français",
        niveau="L2",
        difficulte="Moyen",
        signaux_recurrents=0,
    )
    assert result["strategie"] == STRATEGIE_STANDARD


def test_quiz_complexe_utilise_la_verification_renforcee():
    questions = [_question()] * 20
    questions[0]["question"] = "Calculer une équation différentielle avec une intégrale."
    result = analyser_risque(
        questions,
        matiere="Mathématiques",
        niveau="L3",
        difficulte="Difficile",
        signaux_recurrents=5,
    )
    assert result["strategie"] == STRATEGIE_RENFORCEE
    assert "contenu_technique" in result["raisons"]
    assert "erreurs_recurrentes" in result["raisons"]
