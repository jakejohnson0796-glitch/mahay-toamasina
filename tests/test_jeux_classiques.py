from app.jeux_classiques_router import QUESTIONS, calculer, mot_valide, normaliser


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


def test_calcul_atteint_cible():
    assert calculer("(100 - 25) * 4", [100, 25, 4, 3, 2, 1], 300)[0]


def test_calcul_refuse_nombres_non_tires():
    assert not calculer("999 + 1", [100, 25, 4, 3, 2, 1], 1000)[0]


def test_calcul_refuse_expression_invalide_et_division_zero():
    assert not calculer("import os", [1, 2, 3], 0)[0]
    assert not calculer("4 / 0", [4, 2], 2)[0]
