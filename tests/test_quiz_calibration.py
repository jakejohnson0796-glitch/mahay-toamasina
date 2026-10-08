import json

from app.models import TentativeQuiz
from app.quiz_calibration import (
    diagnostic_confiance,
    fusionner_confiances,
    lire_confiances,
    normaliser_confiances,
)


QUESTIONS = [
    {"index_bonne_reponse": 0},
    {"index_bonne_reponse": 0},
    {"index_bonne_reponse": 0},
    {"index_bonne_reponse": 0},
    {"index_bonne_reponse": 0},
]


def _tentative():
    return TentativeQuiz(
        id=42,
        utilisateur_id=7,
        matiere="Mathématiques",
        niveau="L1",
        difficulte="Moyen",
        nb_questions=5,
        questions_json=json.dumps([
            {"question": "a", "choix": ["A"], "index_bonne_reponse": 0},
        ]),
    )


def test_normaliser_confiances_ignore_les_valeurs_invalides():
    assert normaliser_confiances(["forte", "n'importe quoi", None], 4) == [
        "forte",
        None,
        None,
        None,
    ]


def test_fusionner_et_lire_confiances_preserve_les_reponses():
    tentative = _tentative()
    tentative.reponses_json = json.dumps([0, 1, None, 0, 0])

    fusionner_confiances(tentative, ["forte", "faible", None, "moyenne", None])

    donnees = json.loads(tentative.reponses_json)
    assert donnees["reponses"] == [0, 1, None, 0, 0]
    assert lire_confiances(tentative) == ["forte", "faible", None, "moyenne", None]


def test_diagnostic_detecte_une_surconfiance():
    tentative = _tentative()
    tentative.reponses_json = json.dumps({
        "reponses": [1, 1, 0, 0, 0],
        "confiances": ["forte", "forte", "faible", "moyenne", "forte"],
    })

    diagnostic = diagnostic_confiance(
        tentative,
        questions=QUESTIONS,
    )

    assert diagnostic["statut"] == "surconfiance"
    assert diagnostic["surconfiances"] == 2
    assert diagnostic["sousconfiances"] == 1
    assert diagnostic["nb_observations"] == 5


def test_diagnostic_reste_prudent_avec_trop_peu_de_jugements():
    tentative = _tentative()
    tentative.reponses_json = json.dumps({
        "reponses": [0, 1, None, None, None],
        "confiances": ["faible", "forte", None, None, None],
    })

    diagnostic = diagnostic_confiance(
        tentative,
        questions=QUESTIONS,
    )

    assert diagnostic["statut"] == "en_observation"
    assert diagnostic["nb_observations"] == 2
