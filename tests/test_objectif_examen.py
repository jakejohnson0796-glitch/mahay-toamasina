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


def test_cepe_est_un_objectif_pedagogique_non_officiel_pour_t5():
    resultat = construire_contexte_examen("CEPE")

    assert resultat["code"] == "cepe"
    assert resultat["label"] == "CEPE · Classe T5"
    assert "entraînement pédagogique" in resultat["instruction"]
    assert "sujet officiel" in resultat["instruction"]


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


def test_page_objectif_examen_propose_cepe_en_t5_et_modification_profil_scolaire():
    template = lire("app/templates/objectif_examen.html")
    route = lire("app/routers/quiz_router.py")
    profil = lire("app/routers/auth_router.py")

    assert "CEPE · Classe T5" in template
    assert 'name="objectif" value="cepe"' in template
    assert 'href="/profil/scolaire"' in template
    assert 'contexte.get("cycle_education") != "primaire"' in route
    assert '@router.get("/profil/scolaire")' in profil
    assert '"/profil/scolaire?erreur=profil_scolaire_incomplet"' in route
    assert '"T1"' in lire("app/quiz.py")
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

def test_ressources_externes_sont_filtrees_pour_le_primaire():
    from app.ressources_examens import ressources_pour_cycle

    ressources = ressources_pour_cycle("primaire")

    assert [item["id"] for item in ressources] == ["men-rape-t5-cepe"]
    assert all(item["examens_affiches"] == ("cepe",) for item in ressources)
    assert ressources[0]["url"].endswith("/RAPE_T5.pdf")


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
    assert '@router.post("/objectif-examen/programme")' in route
    assert 'bepc_2027_parcours' in route
    assert 'Document.bepc_session_2027_parcours == bepc_parcours' in route
    assert "Annales et ressources externes" in template
    assert "Annales et corrigés de ton niveau" in template
    assert "Publication et exactitude pédagogique sont deux contrôles différents" in template
    assert "Les documents BEPC 2027 affichés respectent le programme déclaré" in template
    assert 'href="/documents/{{ doc.id }}/telecharger"' in template
    assert 'target="_blank" rel="noopener noreferrer"' in template
    assert "ne validons pas individuellement chaque sujet ou corrigé" in template
    assert "Nous ne recopions pas leurs fichiers" in template
    assert "contenus de tiers comme vérifiés ou officiels" in module

class _ExecDocuments:
    def __init__(self, documents):
        self.documents = documents

    def all(self):
        return self.documents


class _SessionDocuments:
    def __init__(self, documents=None, options=None):
        self.documents = documents or []
        self.options = options or {}
        self.query = None

    def get(self, model, option_id):
        return self.options.get(option_id)

    def exec(self, query):
        self.query = query
        return _ExecDocuments(self.documents)


def test_annales_objectif_examen_ne_retourne_rien_sans_profil_scolaire():
    from app.routers.quiz_router import _annales_scolaires_objectif_examen

    session = _SessionDocuments([SimpleNamespace(id=1)])

    assert _annales_scolaires_objectif_examen(session, None) == []
    assert session.query is None


def test_annales_objectif_examen_limite_aux_documents_scolaires_publics():
    from app.routers.quiz_router import _annales_scolaires_objectif_examen

    documents = [SimpleNamespace(id=12), SimpleNamespace(id=11)]
    session = _SessionDocuments(documents)

    resultat = _annales_scolaires_objectif_examen(
        session,
        {
            "niveau_scolaire_id": 3,
            "option_scolaire_id": None,
            "etablissement_scolaire_id": None,
        },
    )

    sql = str(session.query).casefold()
    assert resultat == documents
    assert "document.statut" in sql
    assert "document.portee_academique" in sql
    assert "document.niveau_scolaire_id" in sql
    assert "document.type_document" in sql
    assert "document.cercle_id is null" in sql
    assert "document.option_scolaire_id is null" in sql
    assert "document.etablissement_scolaire_id is null" in sql
    assert "document.annee desc" in sql
    assert "limit" in sql


def test_annales_objectif_examen_accepte_option_fille_et_filtre_etablissement():
    from app.routers.quiz_router import _annales_scolaires_objectif_examen

    option_fille = SimpleNamespace(id=8, parent_option_id=7)
    session = _SessionDocuments(
        [SimpleNamespace(id=14)],
        options={8: option_fille},
    )

    _annales_scolaires_objectif_examen(
        session,
        {
            "niveau_scolaire_id": 4,
            "option_scolaire_id": 8,
            "etablissement_scolaire_id": 20,
        },
        limite=50,
    )

    sql = str(session.query).casefold()
    assert "document.option_scolaire_id is null" in sql
    assert "document.option_scolaire_id in" in sql
    assert "document.etablissement_scolaire_id is null" in sql
    assert "document.etablissement_scolaire_id =" in sql
    assert "limit" in sql

@pytest.mark.parametrize(
    "code",
    ["pe", "ps_a", "ps_b"],
)
def test_valide_les_choix_de_programme_be_pc_2027_pour_une_3e(code):
    from app.routers.quiz_router import _valider_parcours_bepc_2027

    contexte = {"cycle_education": "college", "niveau": "3e"}

    assert _valider_parcours_bepc_2027(code.upper(), contexte) == code


@pytest.mark.parametrize(
    "code,contexte",
    [
        ("", {"cycle_education": "college", "niveau": "3e"}),
        ("option_c", {"cycle_education": "college", "niveau": "3e"}),
        ("pe", {"cycle_education": "college", "niveau": "4e"}),
        ("ps_a", {"cycle_education": "lycee", "niveau": "Terminale"}),
        ("ps_b", None),
    ],
)
def test_refuse_les_choix_be_pc_2027_invalides_ou_hors_3e(code, contexte):
    from app.routers.quiz_router import _valider_parcours_bepc_2027

    with pytest.raises(ValueError):
        _valider_parcours_bepc_2027(code, contexte)


def test_annales_be_pc_2027_sont_filtrees_par_le_programme_du_profil():
    from app.routers.quiz_router import _annales_scolaires_objectif_examen

    session = _SessionDocuments([SimpleNamespace(id=33)])
    contexte = {
        "niveau_scolaire_id": 3,
        "cycle_education": "college",
        "niveau": "3e",
        "option_scolaire_id": None,
        "etablissement_scolaire_id": None,
    }

    _annales_scolaires_objectif_examen(session, contexte, bepc_parcours="ps_b")

    sql = str(session.query).casefold()
    assert "document.annee !=" in sql
    assert "document.bepc_session_2027_parcours =" in sql


def test_annales_be_pc_2027_sont_masquees_si_le_profil_n_a_pas_de_choix():
    from app.routers.quiz_router import _annales_scolaires_objectif_examen

    session = _SessionDocuments([SimpleNamespace(id=34)])
    contexte = {
        "niveau_scolaire_id": 3,
        "cycle_education": "college",
        "niveau": "3e",
        "option_scolaire_id": None,
        "etablissement_scolaire_id": None,
    }

    _annales_scolaires_objectif_examen(session, contexte)

    sql = str(session.query).casefold()
    assert "document.annee !=" in sql
    assert "document.bepc_session_2027_parcours =" not in sql
