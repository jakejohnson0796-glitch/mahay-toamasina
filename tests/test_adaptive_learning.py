from types import SimpleNamespace

from app.adaptive_learning import appliquer_etat, transition_apres_quiz


def test_score_faible_retourne_au_tuteur():
    decision = transition_apres_quiz(40, False)
    assert decision["etape"] == "comprendre"
    assert decision["statut"] == "active"
    assert "fragile" in decision["feedback"]


def test_score_moyen_demande_une_pratique_ciblee():
    decision = transition_apres_quiz(60, False)
    assert decision["etape"] == "pratiquer"
    assert decision["statut"] == "active"


def test_bon_score_sans_preuve_ne_termine_pas_la_mission():
    decision = transition_apres_quiz(100, False)
    assert decision["etape"] == "verifier"
    assert decision["statut"] == "active"


def test_mission_est_terminee_uniquement_si_maitrise_confirmee():
    decision = transition_apres_quiz(80, True)
    assert decision["etape"] == "terminee"
    assert decision["statut"] == "terminee"


def test_vue_persistante_selectionne_la_bonne_action():
    mission = {"active": True, "titre": "Mission", "etapes": [
        {"titre": "Comprendre", "etat": "prioritaire"},
        {"titre": "Pratiquer", "etat": "a_faire"},
        {"titre": "Vérifier", "etat": "a_faire"},
    ]}
    etat = SimpleNamespace(
        id=12, statut="active", etape="verifier",
        nb_tentatives=2, dernier_score=90,
        dernier_feedback="Une preuve supplémentaire est nécessaire.",
    )
    vue = appliquer_etat(mission, etat)
    assert vue["mission_id"] == 12
    assert vue["action_principale"] == "quiz"
    assert vue["etape_courante"] == "verifier"
    assert vue["etapes"][2]["etat"] == "prioritaire"
    assert vue["dernier_score"] == 90
