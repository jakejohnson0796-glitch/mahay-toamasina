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


def test_prochaine_notion_ne_depasse_pas_un_prerequis_non_confirme():
    from app.adaptive_learning import choisir_prochaine_notion

    progressions = [
        SimpleNamespace(id=1, matiere="Mathématiques", notion="Matrices", score_maitrise=76, nb_erreurs=1, maitrise_confirmee=False),
        SimpleNamespace(id=2, matiere="Mathématiques", notion="Déterminants", score_maitrise=40, nb_erreurs=3, maitrise_confirmee=False),
        SimpleNamespace(id=3, matiere="Mathématiques", notion="Systèmes", score_maitrise=25, nb_erreurs=4, maitrise_confirmee=False),
    ]
    carte = {"sujets": [{"nodes": [
        {"id": 1, "matiere": "Mathématiques", "notion": "Matrices", "score": 76, "prerequis": []},
        {"id": 2, "matiere": "Mathématiques", "notion": "Déterminants", "score": 40, "prerequis": ["Matrices"]},
        {"id": 3, "matiere": "Mathématiques", "notion": "Systèmes", "score": 25, "prerequis": ["Déterminants"]},
    ]}]}

    suivante = choisir_prochaine_notion(carte, progressions, exclure_id=99)
    assert suivante["notion"] == "Matrices"


def test_prochaine_notion_autorise_un_dependant_quand_prerequis_confirme():
    from app.adaptive_learning import choisir_prochaine_notion

    progressions = [
        SimpleNamespace(id=1, matiere="Mathématiques", notion="Matrices", score_maitrise=92, nb_erreurs=0, maitrise_confirmee=True),
        SimpleNamespace(id=2, matiere="Mathématiques", notion="Déterminants", score_maitrise=50, nb_erreurs=2, maitrise_confirmee=False),
    ]
    carte = {"sujets": [{"nodes": [
        {"id": 1, "matiere": "Mathématiques", "notion": "Matrices", "score": 92, "prerequis": []},
        {"id": 2, "matiere": "Mathématiques", "notion": "Déterminants", "score": 50, "prerequis": ["Matrices"]},
    ]}]}

    suivante = choisir_prochaine_notion(carte, progressions, exclure_id=1)
    assert suivante["notion"] == "Déterminants"


def test_aucune_notion_non_confirmee_ne_propose_pas_de_nouvelle_mission():
    from app.adaptive_learning import choisir_prochaine_notion

    progression = SimpleNamespace(id=1, matiere="Mathématiques", notion="Matrices", score_maitrise=95, nb_erreurs=0, maitrise_confirmee=True)
    carte = {"sujets": [{"nodes": [
        {"id": 1, "matiere": "Mathématiques", "notion": "Matrices", "score": 95, "prerequis": []},
    ]}]}
    assert choisir_prochaine_notion(carte, [progression], exclure_id=1) is None
