from pathlib import Path
from types import SimpleNamespace

import pytest

from app.objectif_examen import construire_contexte_examen
from app.routers.quiz_router import _libelle_serie_baccalaureat


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
    assert "programme d'études (pe)" in pe["label"].casefold()
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
    assert "10 questions et 15 minutes" in template
    assert "ne reproduit pas la durée" in template
    assert "BEPC · Session 2027" in template


class _SessionOptions:
    def __init__(self, options):
        self.options = options

    def get(self, model, option_id):
        return self.options.get(option_id)


def test_serie_baccalaureat_accepte_une_serie_verifiee():
    serie = SimpleNamespace(
        id=10, referentiel_id=2, niveau_id=7, code='D', libelle='Série D',
        type_option='serie', est_active=True, statut_validation='verifie',
        parent_option_id=None,
    )
    assert _libelle_serie_baccalaureat(_SessionOptions({}), serie) == 'D · Série D'


def test_serie_baccalaureat_accepte_une_option_fille_avec_parent_verifie():
    parent = SimpleNamespace(
        id=10, referentiel_id=2, niveau_id=7, code='S', libelle='Série S',
        type_option='serie', est_active=True, statut_validation='verifie',
        parent_option_id=None,
    )
    enfant = SimpleNamespace(
        id=11, referentiel_id=2, niveau_id=7, code='Option D', libelle='Option D',
        type_option='option', est_active=True, statut_validation='verifie',
        parent_option_id=10,
    )
    assert _libelle_serie_baccalaureat(_SessionOptions({10: parent}), enfant) == 'S · Série S — Option D · Option D'


def test_serie_baccalaureat_refuse_option_avec_parent_non_verifie():
    parent = SimpleNamespace(
        id=10, referentiel_id=2, niveau_id=7, code='S', libelle='Série S',
        type_option='serie', est_active=True, statut_validation='a_verifier',
        parent_option_id=None,
    )
    enfant = SimpleNamespace(
        id=11, referentiel_id=2, niveau_id=7, code='Option D', libelle='Option D',
        type_option='option', est_active=True, statut_validation='verifie',
        parent_option_id=10,
    )
    assert _libelle_serie_baccalaureat(_SessionOptions({10: parent}), enfant) is None

def test_ressources_externes_sont_filtrees_pour_le_college():
    from app.ressources_examens import ressources_pour_cycle

    ressources = ressources_pour_cycle("college")

    assert [item["id"] for item in ressources] == ["laza-adina"]
    assert all(item["examens_affiches"] == ("bepc",) for item in ressources)


def test_ressources_externes_sont_filtrees_pour_le_lycee():
    from app.ressources_examens import ressources_pour_cycle

    ressources = ressources_pour_cycle("lycee")

    assert {item["id"] for item in ressources} == {"laza-adina", "madagasy-exams"}
    assert all(item["examens_affiches"] == ("baccalaureat",) for item in ressources)


def test_ressources_externes_restent_explicitement_non_validees_par_mitaridala():
    from app.ressources_examens import ressources_pour_cycle

    ressources = ressources_pour_cycle(None)

    assert len(ressources) == 2
    for ressource in ressources:
        assert ressource["url"].startswith("https://")
        assert ressource["description"]
        assert ressource["limites"]
        assert ressource["source_note"]


def test_page_objectif_examen_presente_les_sources_externes_avec_liens_proteges():
    template = lire("app/templates/objectif_examen.html")
    route = lire("app/routers/quiz_router.py")
    module = lire("app/ressources_examens.py")

    assert "ressources_examens.ressources_pour_cycle(cycle)" in route
    assert "Annales et ressources externes" in template
    assert 'target="_blank" rel="noopener noreferrer"' in template
    assert "ne validons pas individuellement chaque sujet ou corrigé" in template
    assert "Nous ne recopions pas leurs fichiers" in template
    assert "contenus de tiers comme vérifiés ou officiels" in module
