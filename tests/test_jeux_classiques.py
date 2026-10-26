from pathlib import Path

from app.jeux_classiques_router import (
    MOTS,
    QUESTIONS,
    calculer,
    effacer_partie_classique,
    mot_valide,
    normaliser,
    tirer_lettres,
)


def test_banque_questions_coherente():
    assert len({q["id"] for q in QUESTIONS}) == len(QUESTIONS)
    for q in QUESTIONS:
        assert q["question"].strip()
        assert 0 <= q["bonne"] < len(q["choix"])
        assert q["explication"].strip()


def test_normalisation_accents_et_casse():
    assert normaliser("École") == "ECOLE"


def test_mot_lettres_disponibles():
    assert mot_valide("ARBRE", list("ARBRE"))
    assert not mot_valide("ARBRE", list("ARBE"))


def test_tirage_lettres_contient_au_moins_un_mot_jouable():
    for _ in range(50):
        lettres = tirer_lettres()
        assert len(lettres) == 9
        assert any(mot_valide(mot, lettres) for mot in MOTS)


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


def test_template_affiche_une_action_reelle_pour_changer_de_jeu():
    template = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "templates"
        / "jeux_classiques.html"
    ).read_text(encoding="utf-8")

    assert 'action="/jeux-classiques/changer"' in template
    assert 'name="_csrf"' in template
    assert "Changer de jeu" in template
    assert "Choisir un autre jeu" in template
