import json
from types import SimpleNamespace

import pytest

from app import ai_ensemble
from app.ai_quiz import OUTIL_QUIZ
from app.json_latex import charger_json_ia
from app.quiz_validation import QuizValidationError, valider_questions


def _completion_with_content(payload):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(payload, ensure_ascii=False),
                    tool_calls=None,
                )
            )
        ]
    )


def test_groq_strict_schema_ferme_tous_les_objets_et_exige_tous_les_champs():
    response_format = ai_ensemble.structured_response_format(
        "openai/gpt-oss-120b",
        OUTIL_QUIZ["function"]["parameters"],
        "soumettre_quiz",
    )

    assert response_format["type"] == "json_schema"
    schema = response_format["json_schema"]
    assert schema["strict"] is True
    quiz_schema = schema["schema"]
    assert quiz_schema["additionalProperties"] is False

    question_schema = quiz_schema["properties"]["questions"]["items"]
    assert question_schema["additionalProperties"] is False
    assert set(question_schema["required"]) == set(question_schema["properties"])

    # Ces contraintes restent volontairement au validateur applicatif.
    choix_schema = question_schema["properties"]["choix"]
    assert "minItems" not in choix_schema
    assert "maxItems" not in choix_schema
    assert "uniqueItems" not in choix_schema


def test_groq_structured_content_preserve_un_latex_reel():
    payload = {
        "questions": [
            {
                "question": r"Calcule (\frac{1}{x-3}) pour (x=4).",
                "choix": [r"(1)", r"(\frac{1}{2})", r"(0)", r"(-1)"],
                "index_bonne_reponse": 0,
                "explication": r"On obtient (1/(4-3)=1).",
                "difficulte": "Facile",
                "notion": "Fraction rationnelle",
            }
        ]
    }
    completion = _completion_with_content(payload)

    parsed = ai_ensemble._extract_structured_content(completion)

    assert parsed == payload
    assert r"\frac" in parsed["questions"][0]["question"]


def test_chargeur_json_ia_repare_les_antislashs_latex_apres_json_invalide():
    brut = r'{"question":"(\frac{1}{x-3})"}'
    parsed = charger_json_ia(brut)

    assert parsed["question"] == r"(rac{1}{x-3})"


def test_validation_bloque_les_choix_dupliques():
    questions = [
        {
            "question": "Question",
            "choix": ["A", "A", "B", "C"],
            "index_bonne_reponse": 0,
            "explication": "A est la bonne reponse.",
            "difficulte": "Facile",
            "notion": "Test",
        }
    ]

    with pytest.raises(QuizValidationError, match="doivent etre distincts"):
        valider_questions(questions, expected_count=1, strict_coherence=True)
