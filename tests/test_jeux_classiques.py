import random
import time
from pathlib import Path

from app.jeux_classiques_router import (
    ENIGMES,
    MOTS,
    QUESTIONS,
    calculer,
    creer_partie_champion,
    effacer_partie_classique,
    melanger_choix,
    mot_valide,
    normaliser,
    preparer_question_active,
    preparer_questions_tournoi,
    selectionner_questions_champion,
    TEMPS_CHIFFRES,
    TEMPS_LETTRES,
    TEMPS_QUESTION_CHAMPION,
    tirer_chiffres,
    tirer_lettres,
    tirer_tirage_lettres,
)


def test_banque_questions_variee_et_coherente():
    assert len(QUESTIONS) >= 4_000
    assert sum(q['type_question'] == 'calcul' for q in QUESTIONS) >= 4_000
    assert len(ENIGMES) >= 18
    assert {q["difficulte"] for q in ENIGMES} == {"facile", "moyen", "difficile"}
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
    assert len(MOTS) >= 10_000
    assert mot_valide('CHAT', list('CHAT'))


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



def test_chaque_partie_competitive_contient_des_enigmes_du_niveau_choisi():
    for difficulte in ("facile", "moyen", "difficile"):
        questions = selectionner_questions_champion(difficulte, random.Random(31))
        enigmes = [q for q in questions if q["type_question"] == "enigme"]
        assert len(questions) == 10
        assert len(enigmes) == 4
        assert all(q["difficulte"] == difficulte for q in enigmes)
        assert len({q["id"] for q in questions}) == 10


def test_tournoi_fige_les_propositions_et_la_bonne_reponse():
    paquet = preparer_questions_tournoi("difficile", random.Random(17))
    assert len(paquet) == 10
    assert sum(q["type_question"] == "enigme" for q in paquet) == 4
    for item in paquet:
        assert len(item["choix"]) == 4
        original = next(q for q in QUESTIONS if q["id"] == item["id"])
        assert item["choix"][item["bonne"]] == original["choix"][original["bonne"]]
        assert item["explication"] == original["explication"]


def test_interface_conserve_le_tournoi_et_supprime_le_bot():
    racine = Path(__file__).resolve().parents[1]
    page_jeu = (racine / "app" / "templates" / "jeux_classiques.html").read_text(encoding="utf-8")
    page_tournoi = (racine / "app" / "templates" / "jeux_classiques_tournoi.html").read_text(encoding="utf-8")
    migration = (racine / "alembic" / "versions" / "bca6e2d8f143_tournoi_questions_champion.py").read_text(encoding="utf-8")

    assert 'name="mode" value="champion_bot"' not in page_jeu
    assert "Défier un bot" not in page_jeu
    assert "champion_bot" not in page_jeu
    assert 'name="mode" value="champion"' in page_jeu
    assert 'option value="facile"' in page_jeu
    assert 'option value="moyen"' in page_jeu
    assert 'option value="difficile"' in page_jeu
    assert "/jeux-classiques/tournoi" in page_jeu
    assert 'action="/jeux-classiques/tournoi/creer"' in page_tournoi
    assert 'action="/jeux-classiques/tournoi/rejoindre"' in page_tournoi
    assert "Actualiser le salon" in page_tournoi
    assert 'down_revision: Union[str, None] = "d5e9c7a1b3f6"' in migration
    assert "uq_reponse_tournoi_joueur_manche" in migration

def test_questions_supplementaires_sont_uniques_et_variees():
    identifiants = [question["id"] for question in QUESTIONS]
    assert len(identifiants) == len(set(identifiants))
    assert sum(question["theme"] == "Géographie" for question in QUESTIONS) >= 50
    assert sum(question["type_question"] == "calcul" for question in QUESTIONS) >= 4_000
    for question in random.sample(QUESTIONS, min(100, len(QUESTIONS))):
        assert len(question["choix"]) == 4
        assert len(set(question["choix"])) == 4
        assert 0 <= question["bonne"] < 4
        assert question["question"].strip()
        assert question["explication"].strip()


def test_chaque_jeu_a_une_echeance_serveur():
    champion = creer_partie_champion(random.Random(42))
    assert TEMPS_QUESTION_CHAMPION == 20
    assert champion["echeance"] > time.time()
    assert champion["temps_max"] == TEMPS_QUESTION_CHAMPION
    assert TEMPS_CHIFFRES == 120
    assert TEMPS_LETTRES == 90


def test_template_affiche_les_minuteurs_et_timeout_tournoi():
    racine = Path(__file__).resolve().parents[1]
    page_jeu = (racine / "app" / "templates" / "jeux_classiques.html").read_text(encoding="utf-8")
    page_tournoi = (racine / "app" / "templates" / "jeux_classiques_tournoi.html").read_text(encoding="utf-8")
    assert page_jeu.count('data-minuteur data-echeance=') >= 3
    assert "data-minuteur-timeout" in page_jeu
    assert "data-minuteur data-echeance=" in page_tournoi
    assert "data-minuteur-timeout" in page_tournoi
    assert "Retirer la dernière lettre" in page_jeu
    assert "data-compte-calculatrice" in page_jeu


def test_interface_compte_est_bon_propose_un_clavier_de_calcul_interactif():
    template = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "templates"
        / "jeux_classiques.html"
    ).read_text(encoding="utf-8")

    assert 'data-compte-calculatrice' in template
    assert 'data-expression-input' in template
    assert 'data-numero="{{ n }}"' in template
    assert 'data-operation="+"' in template
    assert 'data-operation="−"' in template
    assert 'data-operation="×"' in template
    assert 'data-operation="÷"' in template
    assert 'data-operation="("' in template
    assert 'data-operation=")"' in template
    assert 'data-calcul-action="annuler"' in template
    assert 'data-calcul-action="effacer"' in template
    assert 'name="reponse"' in template
    assert 'csp_nonce(request)' in template

def test_interface_mot_le_plus_long_propose_un_tirage_interactif():
    template = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "templates"
        / "jeux_classiques.html"
    ).read_text(encoding="utf-8")

    assert 'data-mot-long' in template
    assert 'data-lettre="{{ lettre|upper }}"' in template
    assert 'data-mot-input' in template
    assert 'data-mot-action="annuler"' in template
    assert 'data-mot-action="effacer"' in template
    assert "normaliserLettres" in template
    assert "points si le mot est accepté" in template
    assert 'action="/jeux-classiques/repondre"' in template
    assert 'csp_nonce(request)' in template

