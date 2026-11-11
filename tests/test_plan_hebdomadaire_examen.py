from datetime import datetime
from pathlib import Path

from app.preparation_intelligente import construire_plan_hebdomadaire


def _bilan(matiere, statut, score=None, nb_a_revoir=0, resume="Bilan observé."):
    return {
        "matiere": matiere,
        "statut": statut,
        "score": score,
        "nb_a_revoir": nb_a_revoir,
        "resume": resume,
    }


def test_plan_hebdomadaire_priorise_les_matieres_non_evaluees_et_fragiles():
    depart = datetime(2026, 11, 11, 9, 0)
    bilans = [
        _bilan("Sciences", "en_consolidation", 72, 1),
        _bilan("Français", "a_renforcer", 42, 3),
        _bilan("Mathématiques", "a_evaluer"),
        _bilan("Histoire", "a_confirmer", 88, 1),
    ]

    plan = construire_plan_hebdomadaire(
        bilans,
        maintenant=depart,
        objectif="bepc_ps",
        option_ps="B",
    )

    assert len(plan["seances"]) == 7
    assert plan["nb_matieres"] == 4
    assert plan["duree_totale_minutes"] == 120
    assert plan["seances"][0]["titre"] == "Diagnostic initial · Mathématiques"
    assert plan["seances"][0]["objectif"] == "bepc_ps"
    assert plan["seances"][0]["option_ps"] == "B"
    assert plan["seances"][2]["titre"] == "Renforcement ciblé · Français"
    assert plan["seances"][5]["titre"] == "Vérification des acquis · Histoire"
    assert plan["seances"][6]["titre"] == "Bilan de la semaine"
    assert plan["seances"][6]["href"] == "/mon-parcours"
    assert [seance["date_label"] for seance in plan["seances"]] == [
        "11/11", "12/11", "13/11", "14/11", "15/11", "16/11", "17/11"
    ]


def test_plan_alterne_entrainement_et_correction_active():
    plan = construire_plan_hebdomadaire(
        [
            _bilan("Mathématiques", "a_renforcer", 38, 4),
            _bilan("Français", "a_evaluer"),
        ],
        maintenant=datetime(2026, 11, 11),
        objectif="cepe",
    )

    assert plan["seances"][0]["objectif"] == "cepe"
    assert plan["seances"][1]["href"] == "/mes-revisions"
    assert plan["seances"][1]["objectif"] is None
    assert plan["seances"][2]["matiere"] == "Français"
    assert plan["seances"][3]["href"] == "/mes-revisions"
    assert plan["seances"][4]["matiere"] == "Français"
    assert plan["seances"][4]["titre"].startswith("Vérifier tes progrès")


def test_parcours_bepc_ps_sans_option_valide_ne_cree_pas_de_formulaire_invalide():
    plan = construire_plan_hebdomadaire(
        [_bilan("Mathématiques", "a_evaluer")],
        maintenant=datetime(2026, 11, 11),
        objectif="bepc_ps",
        option_ps="C",
        lien_quiz="/objectif-examen#choisir-examen",
    )

    premiere_seance = plan["seances"][0]
    assert premiere_seance["objectif"] is None
    assert premiere_seance["href"] == "/objectif-examen#choisir-examen"


def test_plan_vide_ne_fabrique_pas_de_diagnostic_ou_de_score():
    plan = construire_plan_hebdomadaire([], maintenant=datetime(2026, 11, 11))

    assert plan == {
        "seances": [],
        "nb_matieres": 0,
        "duree_totale_minutes": 0,
    }


def test_plan_ignore_les_matieres_dupliquees_et_borne_les_objectifs():
    plan = construire_plan_hebdomadaire(
        [
            _bilan("Physique", "a_evaluer"),
            _bilan(" physique ", "maitrisee", 96),
        ],
        maintenant=datetime(2026, 11, 11),
        objectif="inconnu",
    )

    assert plan["nb_matieres"] == 1
    assert plan["seances"][0]["matiere"] == "Physique"
    assert plan["seances"][0]["objectif"] is None
    assert plan["seances"][0]["href"] == "/quiz"


def test_page_objectif_examen_affiche_le_programme_hebdomadaire_dynamique():
    root = Path(__file__).resolve().parents[1]
    route = (root / "app/routers/quiz_router.py").read_text(encoding="utf-8")
    template = (root / "app/templates/objectif_examen.html").read_text(encoding="utf-8")
    style = (root / "app/static/objectif-examen.css").read_text(encoding="utf-8")

    assert "preparation_intelligente.construire_plan_hebdomadaire" in route
    assert '"plan_hebdomadaire": plan_hebdomadaire' in route
    assert 'id="plan-7-jours"' in template
    assert 'action="/objectif-examen/lancer"' in template
    assert 'action="/mes-revisions"' not in template
    assert ".objectif-examen-semaine-grid" in style
    assert "@media(max-width:640px)" in style
