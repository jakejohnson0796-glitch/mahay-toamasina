from datetime import datetime, timedelta

from app.learning_session import construire_mission
from app.models import ProgressionNotion


def progression(pid, notion, score, erreurs=0, due=None):
    return ProgressionNotion(
        id=pid,
        utilisateur_id=1,
        matiere="Mathématiques",
        notion=notion,
        score_maitrise=score,
        confiance_maitrise=70,
        nb_questions=10,
        nb_revisions=2,
        nb_erreurs=erreurs,
        prochaine_revision_le=due,
    )


def carte(progression_id, notion, score):
    return {
        "prochaine": {
            "id": progression_id,
            "matiere": "Mathématiques",
            "notion": notion,
            "score": score,
        }
    }


def test_mission_faiblesse_commence_par_tuteur():
    p = progression(1, "Déterminants", 42, erreurs=3)
    mission = construire_mission(carte(1, "Déterminants", 42), [p])

    assert mission["active"] is True
    assert mission["action_principale"] == "tuteur"
    assert mission["etapes"][0]["type"] == "tuteur"
    assert mission["etapes"][1]["type"] == "quiz"


def test_mission_en_cours_commence_par_quiz():
    p = progression(2, "Fonctions", 64, erreurs=1)
    mission = construire_mission(carte(2, "Fonctions", 64), [p])

    assert mission["action_principale"] == "quiz"
    assert mission["titre"] == "Stabiliser la notion"
    assert mission["action_secondaire"] == "tuteur"


def test_mission_bonne_maitrise_cherche_une_preuve():
    p = progression(3, "Matrices", 88, erreurs=0)
    mission = construire_mission(carte(3, "Matrices", 88), [p])

    assert mission["action_principale"] == "quiz"
    assert mission["titre"] == "Prouver la maîtrise"


def test_mission_detecte_une_revision_due():
    p = progression(
        4,
        "Dérivées",
        78,
        erreurs=0,
        due=datetime.utcnow() - timedelta(days=1),
    )
    mission = construire_mission(carte(4, "Dérivées", 78), [p])

    assert mission["titre"] == "Stabiliser la notion"
    assert mission["action_principale"] == "quiz"


def test_mission_sans_priorite_reste_non_active():
    mission = construire_mission({"prochaine": None}, [])

    assert mission["active"] is False
    assert mission["etapes"] == []
