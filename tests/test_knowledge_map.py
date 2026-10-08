from app.knowledge_map import construire_carte
from app.models import ProgressionNotion


def progression(pid, matiere, notion, score, confiance=70):
    return ProgressionNotion(
        id=pid,
        utilisateur_id=1,
        matiere=matiere,
        notion=notion,
        score_maitrise=score,
        confiance_maitrise=confiance,
        nb_questions=5,
        nb_revisions=2,
    )


def test_carte_relie_un_prerequis_observe_a_une_notion_dependante():
    carte = construire_carte(
        [
            progression(1, "Mathématiques", "Déterminant d'ordre 2", 45),
            progression(2, "Mathématiques", "Systèmes linéaires", 68),
        ]
    )

    assert carte["nb_notions"] == 2
    assert carte["nb_relations"] == 1
    relation = carte["relations"][0]
    assert relation["source"]["notion"] == "Déterminant d'ordre 2"
    assert relation["target"]["notion"] == "Systèmes linéaires"
    assert relation["source_faible"] is True
    assert carte["prochaine"]["notion"] == "Déterminant d'ordre 2"


def test_carte_ne_invente_pas_de_relation_absente():
    carte = construire_carte(
        [
            progression(1, "Mathématiques", "Déterminant d'ordre 2", 45),
            progression(2, "Mathématiques", "Probabilités", 60),
        ]
    )

    assert carte["nb_notions"] == 2
    assert carte["nb_relations"] == 0
    assert carte["blocages"] == []
    assert {node["notion"] for node in carte["sujets"][0]["nodes"]} == {
        "Déterminant d'ordre 2",
        "Probabilités",
    }


def test_carte_respecte_la_matiere_pour_eviter_un_faux_lien():
    carte = construire_carte(
        [
            progression(1, "Mathématiques", "Fonctions", 60),
            progression(2, "Physique", "Cinématique", 55),
        ]
    )

    assert carte["nb_relations"] == 0


def test_carte_priorise_une_notion_faible_sans_prerequis_connu():
    carte = construire_carte(
        [
            progression(1, "Mathématiques", "Probabilités", 35),
            progression(2, "Mathématiques", "Statistiques", 85),
        ]
    )

    assert carte["prochaine"]["notion"] == "Probabilités"
    assert carte["prochaine"]["score"] == 35
