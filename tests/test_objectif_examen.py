from pathlib import Path

import pytest

from app.objectif_examen import construire_contexte_examen


ROOT = Path(__file__).resolve().parents[1]


def lire(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_bepc_ancien_programme_exige_option_a_ou_b():
    a = construire_contexte_examen("bepc_ps", option_ps="A")
    b = construire_contexte_examen("bepc_ps", option_ps="b")

    assert a["label"] == "BEPC 2027 · Programme scolaire (PS) · Option A"
    assert "option A" in a["instruction"]
    assert "option B" in b["instruction"]
    with pytest.raises(ValueError):
        construire_contexte_examen("bepc_ps")
    with pytest.raises(ValueError):
        construire_contexte_examen("bepc_ps", option_ps="C")


def test_bepc_nouveau_programme_est_distinct_de_ps():
    pe = construire_contexte_examen("bepc_pe")

    assert pe["code"] == "bepc_pe"
    assert "Programme d'études (PE)" in pe["label"]
    assert "Programme scolaire (PS)" not in pe["instruction"]


def test_baccalaureat_exige_une_serie_renseignee():
    resultat = construire_contexte_examen("baccalaureat", serie="Série D")

    assert resultat["label"] == "Baccalauréat · Série D"
    assert "série Série D" in resultat["instruction"]
    with pytest.raises(ValueError):
        construire_contexte_examen("baccalaureat")
    with pytest.raises(ValueError):
        construire_contexte_examen("baccalaureat", serie="x" * 61)


def test_objectif_examen_reste_un_enchainement_des_moteurs_existants():
    route = lire("app/routers/quiz_router.py")
    quiz = lire("app/quiz.py")
    template = lire("app/templates/objectif_examen.html")
    base = lire("app/templates/base.html")

    assert '@router.get("/objectif-examen")' in route
    assert '@router.post("/objectif-examen/lancer")' in route
    assert "creer_tentative_examen" in route
    assert "sujet_cible=sujet_cible" in quiz
    assert "/objectif-examen/lancer" in template
    assert "Entraînement pédagogique, pas sujet officiel" in template
    assert 'href="/objectif-examen"' in base


def test_page_objectif_examen_signale_le_perimetre_cepe_non_raccorde():
    template = lire("app/templates/objectif_examen.html")

    assert "CEPE et primaire" in template
    assert "référentiel primaire" in template
    assert "BEPC 2027" in template
