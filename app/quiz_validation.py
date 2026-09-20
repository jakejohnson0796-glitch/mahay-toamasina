"""Validation locale des quizzes avant stockage ou correction."""
import re
from typing import Any

MAX_QUESTION_CHARS = 800
MAX_CHOIX_CHARS = 300
MAX_EXPLICATION_CHARS = 800
MAX_TOTAL_CHARS = 60_000


class QuizValidationError(ValueError):
    pass


def valider_questions(questions: Any, expected_count: int | None = None) -> list[dict]:
    if not isinstance(questions, list):
        raise QuizValidationError("Le quiz doit etre une liste de questions.")
    if expected_count is not None and len(questions) != expected_count:
        raise QuizValidationError("Le nombre de questions est incorrect.")
    total = 0
    result: list[dict] = []
    for numero, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            raise QuizValidationError(f"La question {numero} est invalide.")
        texte = str(question.get("question", "")).strip()
        choix = question.get("choix")
        explication = str(question.get("explication", "")).strip()
        index = question.get("index_bonne_reponse")
        if not texte or len(texte) > MAX_QUESTION_CHARS:
            raise QuizValidationError(f"Le texte de la question {numero} est invalide.")
        if not isinstance(choix, list) or not 3 <= len(choix) <= 5:
            raise QuizValidationError(f"La question {numero} doit avoir entre 3 et 5 choix.")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(choix):
            raise QuizValidationError(f"L'index de bonne reponse de la question {numero} est invalide.")
        if not explication or len(explication) > MAX_EXPLICATION_CHARS:
            raise QuizValidationError(f"L'explication de la question {numero} est invalide.")
        choix_nettoyes = [str(c).strip() for c in choix]
        if any(not c or len(c) > MAX_CHOIX_CHARS for c in choix_nettoyes):
            raise QuizValidationError(f"Un choix de la question {numero} est invalide.")
        signatures = [re.sub(r"\s+", " ", c).casefold() for c in choix_nettoyes]
        if len(set(signatures)) != len(signatures):
            raise QuizValidationError(f"Les choix de la question {numero} doivent etre distincts.")
        total += len(texte) + len(explication) + sum(len(c) for c in choix_nettoyes)
        if total > MAX_TOTAL_CHARS:
            raise QuizValidationError("Le quiz depasse la taille maximale autorisee.")
        result.append({
            "question": texte,
            "choix": choix_nettoyes,
            "index_bonne_reponse": index,
            "explication": explication,
        })
    return result
