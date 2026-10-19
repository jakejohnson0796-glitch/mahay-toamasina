import json
from types import SimpleNamespace

import pytest

from app import ai_ensemble, ai_quiz
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
    # Construire l'antislash par codepoint pour que le fichier de test lui-même
    # ne transforme pas \\f en caractère de contrôle avant l'appel au parseur.
    brut = '{"question":"(' + chr(92) + 'frac{1}{x-3})"}'
    parsed = charger_json_ia(brut)

    assert parsed["question"] == "(" + chr(92) + "frac{1}{x-3})"

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


def test_generation_groq_ne_depasse_pas_le_budget_tpm_sur_les_reessais(monkeypatch):
    appels = []

    def create_completion(**kwargs):
        appels.append(kwargs)
        # Une réponse invalide force le second essai sans appeler Groq.
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="{}", tool_calls=None),
                    finish_reason="stop",
                )
            ]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create_completion)
        )
    )
    monkeypatch.setattr(ai_quiz.parametres, "groq_model", "openai/gpt-oss-120b")
    monkeypatch.setattr(
        ai_ensemble.cost_controller,
        "call",
        lambda provider, callback: callback(),
    )

    completion, erreur = ai_quiz._generer_completion_avec_reessai(
        client,
        ["consigne initiale", "consigne de secours"],
        max_completion_tokens=2048,
        expected_count=5,
    )

    assert completion is None
    assert erreur is not None
    assert len(appels) == 2
    assert [appel["max_completion_tokens"] for appel in appels] == [2012, 2012]
    assert all(appel["max_completion_tokens"] <= 2048 for appel in appels)



def test_reduction_contexte_quiz_garde_debut_milieu_et_fin_sous_5000_caracteres():
    source = (
        "DEBUT_DOCUMENT\n"
        + ("A" * 14_900)
        + "\nCENTRE_DOCUMENT\n"
        + ("B" * 14_900)
        + "\nFIN_DOCUMENT"
    )

    extrait = ai_quiz._reduire_texte_document_pour_quiz(source)

    assert len(extrait) <= 5_000
    assert "DEBUT_DOCUMENT" in extrait
    assert "CENTRE_DOCUMENT" in extrait
    assert "FIN_DOCUMENT" in extrait
    assert "partie du document omise" in extrait
    assert ai_quiz._reduire_texte_document_pour_quiz("court") == "court"


def test_quiz_document_envoie_un_contexte_borne_a_groq_sans_appel_reseau(monkeypatch):
    appels = []
    payload = {
        "questions": [
            {
                "question": f"Question {i + 1} ?",
                "choix": ["réponse correcte", "distracteur A", "distracteur B", "distracteur C"],
                "index_bonne_reponse": 0,
                "explication": "La première réponse est correcte.",
                "difficulte": "Facile",
                "notion": "Notion du cours",
            }
            for i in range(5)
        ]
    }

    def create_completion(**kwargs):
        appels.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(payload, ensure_ascii=False)),
                    finish_reason="stop",
                )
            ]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create_completion)
        )
    )
    monkeypatch.setattr(ai_quiz, "_obtenir_client", lambda: client)
    monkeypatch.setattr(ai_quiz.parametres, "groq_model", "openai/gpt-oss-120b")
    monkeypatch.setattr(
        ai_ensemble.cost_controller,
        "call",
        lambda provider, callback: callback(),
    )
    source = (
        "DEBUT_DOCUMENT\n"
        + ("A" * 14_900)
        + "\nCENTRE_DOCUMENT\n"
        + ("B" * 14_900)
        + "\nFIN_DOCUMENT"
    )

    questions = ai_quiz.generer_quiz_depuis_texte(source)

    assert len(questions) == 5
    assert len(appels) == 1
    prompt = appels[0]["messages"][0]["content"]
    assert "DEBUT_DOCUMENT" in prompt
    assert "CENTRE_DOCUMENT" in prompt
    assert "FIN_DOCUMENT" in prompt
    assert "partie du document omise" in prompt
    assert len(prompt) < 7_500
    assert appels[0]["max_completion_tokens"] <= 2048
