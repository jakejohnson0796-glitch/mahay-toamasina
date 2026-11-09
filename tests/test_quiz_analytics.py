"""Tests des analyses pedagogiques detaillees des quiz."""

import json
from datetime import datetime
from types import SimpleNamespace

from app import quiz


def _question(enonce, notion):
    return {
        "question": enonce,
        "choix": ["Réponse incorrecte", "Réponse correcte", "Autre possibilité"],
        "index_bonne_reponse": 1,
        "explication": "Explication de test.",
        "notion": notion,
    }


def _tentative(matiere, niveau, questions, reponses, *, date=None):
    return SimpleNamespace(
        matiere=matiere,
        niveau=niveau,
        nb_questions=len(questions),
        questions_json=json.dumps(questions, ensure_ascii=False),
        reponses_json=json.dumps(reponses),
        date_soumission=date or datetime(2026, 11, 1, 12, 0),
    )


def test_statistiques_detaillees_agregent_par_notion_et_question_identique():
    question_addition = _question("Combien vaut 2 + 2 ?", "Addition")
    question_soustraction = _question("Combien vaut 5 - 3 ?", "Soustraction")
    premier = _tentative(
        "Mathématiques",
        "L1",
        [question_addition, question_soustraction],
        [1, 0],
        date=datetime(2026, 11, 1, 12, 0),
    )
    second = _tentative(
        "Mathématiques",
        "L1",
        [question_addition],
        [0],
        date=datetime(2026, 11, 2, 12, 0),
    )

    analyse = quiz.statistiques_detaillees([second, premier])

    assert analyse["nb_tentatives_analysees"] == 2
    assert analyse["nb_questions_analysees"] == 3
    assert analyse["nb_matieres"] == 1
    assert analyse["nb_notions"] == 2

    addition = next(item for item in analyse["notions"] if item["notion"] == "Addition")
    assert addition["nb_questions"] == 2
    assert addition["nb_questions_distinctes"] == 1
    assert addition["nb_reussites"] == 1
    assert addition["nb_erreurs"] == 1
    assert addition["taux_reussite"] == 50

    recurrente = analyse["questions_recurrentes"][0]
    assert recurrente["question"] == "Combien vaut 2 + 2 ?"
    assert recurrente["nb_tentatives"] == 2
    assert recurrente["nb_reussites"] == 1
    assert recurrente["nb_erreurs"] == 1
    assert recurrente["taux_reussite"] == 50
    assert recurrente["derniere_tentative"] == "02/11/2026"


def test_statistiques_detaillees_separent_les_niveaux():
    question = _question("Combien vaut 2 + 2 ?", "Addition")
    l1 = _tentative("Mathématiques", "L1", [question], [1])
    l2 = _tentative("Mathématiques", "L2", [question], [0])

    analyse = quiz.statistiques_detaillees([l1, l2])

    assert analyse["nb_notions"] == 2
    assert {item["niveau"] for item in analyse["notions"]} == {"L1", "L2"}
    assert analyse["nb_questions_recurrentes"] == 0


def test_statistiques_detaillees_comptent_les_absences_de_reponse():
    question = _question("Combien vaut 3 + 3 ?", "Addition")
    tentative = _tentative("Mathématiques", "L1", [question], [None])

    analyse = quiz.statistiques_detaillees([tentative])

    addition = analyse["notions"][0]
    assert addition["nb_questions"] == 1
    assert addition["nb_reussites"] == 0
    assert addition["nb_erreurs"] == 0
    assert addition["nb_sans_reponse"] == 1
    assert addition["taux_reussite"] == 0


def test_statistiques_detaillees_ignorent_les_tentatives_incompletes_ou_invalides():
    question = _question("Combien vaut 4 + 4 ?", "Addition")
    terminee = _tentative("Mathématiques", "L1", [question], [1])
    non_soumise = _tentative("Mathématiques", "L1", [question], [1])
    non_soumise.date_soumission = None
    invalide = SimpleNamespace(
        matiere="Mathématiques",
        niveau="L1",
        nb_questions=1,
        questions_json="pas-du-json",
        reponses_json="[1]",
        date_soumission=datetime(2026, 11, 3, 12, 0),
    )

    analyse = quiz.statistiques_detaillees([non_soumise, invalide, terminee])

    assert analyse["nb_tentatives_analysees"] == 1
    assert analyse["nb_questions_analysees"] == 1
    assert analyse["notions"][0]["nb_reussites"] == 1


def test_statistiques_detaillees_vides_sans_donnees():
    assert quiz.statistiques_detaillees([]) == {
        "nb_tentatives_analysees": 0,
        "nb_questions_analysees": 0,
        "nb_matieres": 0,
        "nb_notions": 0,
        "nb_questions_recurrentes": 0,
        "notions": [],
        "questions_recurrentes": [],
    }
