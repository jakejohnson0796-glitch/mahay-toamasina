from app.models import TentativeQuiz
from app.quiz import (
    DIFFICULTES,
    enregistrer_reponse_adaptative,
    est_quiz_adaptatif,
    etat_adaptatif,
    preparer_questions_adaptatives,
)
from app.quiz_validation import valider_questions


class FakeSession:
    def add(self, obj):
        return None

    def commit(self):
        return None

    def refresh(self, obj):
        return None


def _questions():
    return valider_questions(
        [
            {
                "question": "Q1",
                "choix": ["A", "B", "C"],
                "index_bonne_reponse": 0,
                "explication": "A.",
                "notion": "N",
            },
            {
                "question": "Q2",
                "choix": ["A", "B", "C"],
                "index_bonne_reponse": 0,
                "explication": "A.",
                "notion": "N",
            },
            {
                "question": "Q3",
                "choix": ["A", "B", "C"],
                "index_bonne_reponse": 0,
                "explication": "A.",
                "notion": "N",
            },
            {
                "question": "Q4",
                "choix": ["A", "B", "C"],
                "index_bonne_reponse": 0,
                "explication": "A.",
                "notion": "N",
            },
            {
                "question": "Q5",
                "choix": ["A", "B", "C"],
                "index_bonne_reponse": 0,
                "explication": "A.",
                "notion": "N",
            },
        ],
        expected_count=5,
    )


def _tentative():
    questions = preparer_questions_adaptatives(_questions(), "Moyen")
    return TentativeQuiz(
        id=11,
        utilisateur_id=7,
        matiere="Mathématiques",
        niveau="L1",
        difficulte="Moyen",
        nb_questions=5,
        questions_json='{"questions": ' + __import__("json").dumps(questions, ensure_ascii=False) + ', "adaptatif": true}',
    )


def test_preparer_questions_adaptatives_attribue_trois_niveaux():
    questions = preparer_questions_adaptatives(_questions(), "Moyen")
    assert [q["difficulte"] for q in questions] == [
        "Facile",
        "Moyen",
        "Moyen",
        "Difficile",
        "Difficile",
    ]
    assert set(q["difficulte"] for q in questions) == set(DIFFICULTES)


def test_reponse_correcte_puis_serie_deux_fait_monter_la_difficulte():
    session = FakeSession()
    tentative = _tentative()

    premier = enregistrer_reponse_adaptative(session, tentative, 0, 0)
    assert premier["correcte"] is True
    assert premier["prochaine_question"] == 1

    second = enregistrer_reponse_adaptative(session, tentative, 1, 0)
    assert second["correcte"] is True
    assert second["prochaine_question"] == 3
    assert second["difficulte_suivante"] == "Difficile"
    assert second["serie_reussites"] == 2


def test_erreur_fait_redescendre_vers_une_question_plus_simple():
    session = FakeSession()
    tentative = _tentative()

    enregistrer_reponse_adaptative(session, tentative, 0, 0)
    enregistrer_reponse_adaptative(session, tentative, 1, 0)

    resultat = enregistrer_reponse_adaptative(session, tentative, 3, 1)
    assert resultat["correcte"] is False
    assert resultat["prochaine_question"] == 2
    assert resultat["difficulte_suivante"] == "Moyen"
    assert resultat["serie_reussites"] == 0


def test_etat_adaptatif_reste_compatible_avec_les_reponses_historiques():
    tentative = _tentative()
    assert est_quiz_adaptatif(tentative) is True
    assert etat_adaptatif(tentative)["reponses"] == [None] * 5
