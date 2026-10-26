import random
from pathlib import Path

from app.jeux_classiques_router import (
    MOTS,
    QUESTIONS,
    calculer,
    creer_partie_champion,
    effacer_partie_classique,
    melanger_choix,
    mot_valide,
    normaliser,
    preparer_question_active,
    tirer_chiffres,
    tirer_lettres,
    tirer_tirage_lettres,
)


def test_banque_questions_variee_et_coherente():
    assert len(QUESTIONS) >= 60
    assert len({q["id"] for q in QUESTIONS}) == len(QUESTIONS)
    for question in QUESTIONS:
        assert question["question"].strip()
        assert len(question["choix"]) == 4
        assert len(set(question["choix"])) == 4
        assert 0 <= question["bonne"] < len(question["choix"])
        assert question["explication"].strip()


def test_une_partie_champion_ne_repete_pas_les_questions():
    partie = creer_partie_champion(random.Random(22))
    assert len(partie["ids"]) == 10
    assert len(set(partie["ids"])) == 10
    assert len(partie["choix_actifs"]) == 4
    question = next(q for q in QUESTIONS if q["id"] == partie["ids"][0])
    assert partie["choix_actifs"][partie["bonne_active"]] == question["choix"][question["bonne"]]


def test_les_propositions_peuvent_etre_melangees_sans_perdre_la_correction():
    question = QUESTIONS[0]
    choix, bonne = melanger_choix(question, random.Random(5))
    assert set(choix) == set(question["choix"])
    assert choix[bonne] == question["choix"][question["bonne"]]


def test_preparer_question_active_conserve_la_reponse_apres_rafraichissement():
    partie = creer_partie_champion(random.Random(11))
    choix_avant = list(partie["choix_actifs"])
    bonne_avant = partie["bonne_active"]
    preparer_question_active(partie, random.Random(99))
    assert partie["choix_actifs"] == choix_avant
    assert partie["bonne_active"] == bonne_avant


def test_normalisation_accents_et_casse():
    assert normaliser("École") == "ECOLE"


def test_mot_lettres_disponibles_et_dictionnaire_enrichi():
    assert mot_valide("ARBRE", list("ARBRE"))
    assert not mot_valide("ARBRE", list("ARBE"))
    assert mot_valide("MALAGASY", list("MALAGASY"))
    assert len(MOTS) >= 150


def test_tirage_lettres_contient_au_moins_un_mot_jouable():
    for graine in range(50):
        lettres, solution = tirer_tirage_lettres(random.Random(graine))
        assert len(lettres) == 9
        assert len(solution) <= 9
        assert mot_valide(solution, lettres)
        assert tirer_lettres(random.Random(graine)) == lettres


def test_chiffres_tirage_avec_solution_exacte():
    for graine in range(50):
        nombres, cible, solution, indice = tirer_chiffres(random.Random(graine))
        assert len(nombres) == 6
        assert 101 <= cible <= 999
        assert calculer(solution, nombres, cible)[0]
        assert indice


def test_calcul_atteint_cible_et_accepte_symboles_typographiques():
    assert calculer("(100 - 25) × 4", [100, 25, 4, 3, 2, 1], 300)[0]
    assert calculer("100 ÷ 25 + 4", [100, 25, 4, 3, 2, 1], 8)[0]


def test_calcul_refuse_nombres_non_tires():
    assert not calculer("999 + 1", [100, 25, 4, 3, 2, 1], 1000)[0]


def test_calcul_refuse_expression_invalide_et_division_zero():
    assert not calculer("import os", [1, 2, 3], 0)[0]
    assert not calculer("4 / 0", [4, 2], 2)[0]


def test_changer_jeu_efface_uniquement_la_partie_courante():
    donnees_session = {
        "user_id": 42,
        "autre_preference": "fr",
        "jeux_classiques": {"mode": "champion", "score": 3, "tour": 4},
    }

    effacer_partie_classique(donnees_session)

    assert "jeux_classiques" not in donnees_session
    assert donnees_session["user_id"] == 42
    assert donnees_session["autre_preference"] == "fr"


def test_template_propose_navigation_et_tentatives():
    template = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "templates"
        / "jeux_classiques.html"
    ).read_text(encoding="utf-8")

    assert 'action="/jeux-classiques/changer"' in template
    assert 'action="/jeux-classiques/indice"' in template
    assert 'name="_csrf"' in template
    assert "Changer de jeu" in template
    assert "Rejouer" in template
    assert "tentatives_max" in template
    assert "progress" in template
