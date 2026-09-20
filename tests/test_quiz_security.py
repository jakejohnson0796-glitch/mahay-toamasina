import json

import pytest

from app.quiz import corriger
from app.quiz_validation import QuizValidationError, valider_questions
from app.models import TentativeQuiz


def _questions():
    return [{
        "question": "Combien font 2 + 2 ?",
        "choix": ["3", "4", "5"],
        "index_bonne_reponse": 1,
        "explication": "2 + 2 = 4.",
    }]


class FakeSession:
    def add(self, _obj):
        pass

    def commit(self):
        pass

    def refresh(self, _obj):
        pass


def test_rejects_out_of_range_answer():
    tentative = TentativeQuiz(
        utilisateur_id=1,
        matiere="Maths",
        niveau="L1",
        difficulte="Facile",
        nb_questions=1,
        questions_json=json.dumps(_questions()),
    )
    with pytest.raises(QuizValidationError):
        corriger(FakeSession(), tentative, [7])


def test_rejects_duplicate_choices():
    data = _questions()
    data[0]["choix"] = ["3", "4", "4"]
    with pytest.raises(QuizValidationError):
        valider_questions(data, expected_count=1)


def test_rejects_missing_explanation():
    data = _questions()
    data[0]["explication"] = ""
    with pytest.raises(QuizValidationError):
        valider_questions(data, expected_count=1)
