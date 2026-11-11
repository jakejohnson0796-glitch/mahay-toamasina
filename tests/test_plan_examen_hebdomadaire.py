from datetime import datetime, timedelta
from types import SimpleNamespace

from app.plan_examen_hebdomadaire import construire_plan_hebdomadaire


def _notion(matiere, notion, score, due=None, questions=5, erreurs=2, identifiant=None):
    return SimpleNamespace(
        id=identifiant,
        matiere=matiere,
        notion=notion,
        score_maitrise=score,
        prochaine_revision_le=due,
        nb_questions=questions,
        nb_erreurs=erreurs,
    )


def test_plan_hebdomadaire_priorise_les_revisions_echues_et_niveau_fragile():
    maintenant = datetime(2026, 11, 11, 9, 0)
    echue = _notion("Mathématiques", "Fractions", 75, maintenant - timedelta(hours=1), identifiant=1)
    fragile = _notion("Français", "Accords", 25, maintenant + timedelta(days=2), identifiant=2)
    solide = _notion("Histoire", "Dates", 90, maintenant + timedelta(days=3), identifiant=3)

    plan = construire_plan_hebdomadaire([solide, fragile, echue], maintenant=maintenant)

    assert len(plan) == 7
    assert plan[0]["taches"][0]["notion"] == "Fractions"
    assert plan[0]["taches"][1]["notion"] == "Accords"
    assert plan[1]["taches"][0]["notion"] == "Dates"
    assert plan[0]["duree_minutes"] == 40
    assert plan[2]["taches"] == []


def test_plan_ne_fabrique_pas_de_notion_sans_diagnostic():
    plan = construire_plan_hebdomadaire(
        [_notion("Mathématiques", "Inconnue", 0, questions=0)],
        maintenant=datetime(2026, 11, 11),
    )

    assert len(plan) == 7
    assert all(jour["taches"] == [] for jour in plan)
    assert all(jour["duree_minutes"] == 0 for jour in plan)


def test_plan_est_borne_a_quatorze_notions_et_deux_par_jour():
    maintenant = datetime(2026, 11, 11)
    notions = [
        _notion("Mathématiques", f"Notion {index}", index, identifiant=index)
        for index in range(20)
    ]

    plan = construire_plan_hebdomadaire(notions, maintenant=maintenant, limite_notions=99)

    assert sum(len(jour["taches"]) for jour in plan) == 14
    assert all(len(jour["taches"]) <= 2 for jour in plan)
    assert plan[0]["date_iso"] == "2026-11-11"
    assert plan[-1]["date_iso"] == "2026-11-17"
