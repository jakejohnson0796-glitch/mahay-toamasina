from app.jeux_classiques_router import evaluer_expression, mot_valide, normaliser_texte, tirer_lettres, QUESTIONS


def test_banque_champion_a_des_ids_uniques_et_des_reponses_valides():
    assert len({q["id"] for q in QUESTIONS}) == len(QUESTIONS)
    for q in QUESTIONS:
        assert len(q["choix"]) >= 2
        assert 0 <= q["bonne"] < len(q["choix"])
        assert q["question"].strip() and q["explication"].strip()


def test_normalisation_accents_et_casse():
    assert normaliser_texte("École") == "ECOLE"


def test_lettres_refusent_une_lettre_reutilisee():
    assert mot_valide("ARBRE", list("ARBRE"))
    assert not mot_valide("ARBRE", list("ARBE"))


def test_tirage_lettres_contient_neuf_lettres():
    assert len(tirer_lettres()) == 9


def test_expression_cible_et_rejet_nombres_non_disponibles():
    assert evaluer_expression("(100 - 25) * 4", [100, 25, 4, 3, 2, 1], 300)[0] is True
    ok, _ = evaluer_expression("999 + 1", [100, 25, 4, 3, 2, 1], 1000)
    assert ok is False


def test_expression_refuse_code_ou_division_par_zero():
    assert evaluer_expression("__import__('os')", [1, 2, 3], 0)[0] is False
    assert evaluer_expression("4 / 0", [4, 2], 2)[0] is False
