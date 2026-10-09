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


def _tentative_notion(notion, reponses, confiances, date_soumission):
    tentative = _tentative()
    tentative.matiere = "Mathématiques"
    tentative.nb_questions = len(reponses)
    tentative.questions_json = json.dumps([
        {
            "question": f"Question {index}",
            "choix": ["A", "B"],
            "index_bonne_reponse": 0,
            "notion": notion,
        }
        for index in range(len(reponses))
    ])
    tentative.reponses_json = json.dumps({
        "reponses": reponses,
        "confiances": confiances,
    })
    tentative.date_soumission = date_soumission
    return tentative


def test_carte_illusions_detecte_une_erreur_avec_forte_confiance():
    from datetime import datetime
    from app.quiz_calibration import construire_carte_illusions

    tentative = _tentative_notion(
        "Déterminant d'ordre 2",
        [1, 0, 1],
        ["forte", "moyenne", "forte"],
        datetime(2026, 10, 8, 12, 0, 0),
    )

    cartes = construire_carte_illusions([tentative])

    assert len(cartes) == 1
    assert cartes[0]["notion"] == "Déterminant d'ordre 2"
    assert cartes[0]["erreurs_confiance_forte"] == 2
    assert cartes[0]["observations_fortes"] == 2
    assert cartes[0]["taux_surconfiance"] == 100
    assert cartes[0]["statut"] == "critique"


def test_carte_illusions_ignore_les_notions_sans_erreur_tres_sure():
    from datetime import datetime
    from app.quiz_calibration import construire_carte_illusions

    tentative = _tentative_notion(
        "Matrices",
        [0, 0, 0],
        ["forte", "forte", "faible"],
        datetime(2026, 10, 8, 12, 0, 0),
    )

    assert construire_carte_illusions([tentative]) == []


def test_carte_illusions_priorise_les_signaux_recurrents():
    from datetime import datetime, timedelta
    from app.quiz_calibration import construire_carte_illusions

    date = datetime(2026, 10, 8, 12, 0, 0)
    premier = _tentative_notion(
        "Notion faible",
        [1, 1],
        ["forte", "moyenne"],
        date,
    )
    second = _tentative_notion(
        "Notion faible",
        [1, 1],
        ["forte", "forte"],
        date + timedelta(minutes=5),
    )
    autre = _tentative_notion(
        "Autre notion",
        [1, 0],
        ["forte", "faible"],
        date + timedelta(minutes=10),
    )

    cartes = construire_carte_illusions([autre, premier, second])

    assert cartes[0]["notion"] == "Notion faible"
    assert cartes[0]["erreurs_confiance_forte"] == 3
