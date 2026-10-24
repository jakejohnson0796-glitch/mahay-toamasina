from types import SimpleNamespace

from app import quiz
from app.routers.quiz_router import _niveau_quiz_par_defaut, _suggestion_quiz
from app.templating import templates


def test_le_niveau_scolaire_verifie_prime_sans_etre_demande_dans_le_quiz():
    utilisateur = SimpleNamespace(cycle_education="college", niveau="L1")
    contexte = {"niveau": "3e"}
    progression = SimpleNamespace(niveau="5e")

    assert _niveau_quiz_par_defaut(utilisateur, contexte, [progression], "L2") == "3e"


def test_le_niveau_universitaire_vient_du_profil_avant_l_historique():
    utilisateur = SimpleNamespace(cycle_education="universite", niveau="M1")
    progression = SimpleNamespace(niveau="L2")

    assert _niveau_quiz_par_defaut(utilisateur, None, [progression], "L3") == "M1"


def test_un_ancien_compte_sans_niveau_utilise_sa_progression_connue():
    utilisateur = SimpleNamespace(cycle_education=None, niveau=None)
    progression = SimpleNamespace(niveau="L3")

    assert _niveau_quiz_par_defaut(utilisateur, None, [progression], None) == "L3"


def test_enseignant_du_lycee_sans_classe_individuelle_ne_recoit_pas_un_niveau_universitaire():
    utilisateur = SimpleNamespace(cycle_education="lycee", niveau=None)

    assert _niveau_quiz_par_defaut(utilisateur, None, [], None) == "Seconde"


def test_recommandation_priorise_la_notion_a_revoir_et_adapte_la_difficulte():
    faible = SimpleNamespace(
        matiere="Mathématiques",
        notion="Déterminant",
        niveau="L1",
        score_maitrise=35,
    )
    autre = SimpleNamespace(
        matiere="Français",
        notion="Concordance des temps",
        niveau="L1",
        score_maitrise=65,
    )

    proposition = _suggestion_quiz(["Français", "Mathématiques"], [faible, autre])

    assert proposition["matiere"] == "Mathématiques"
    assert proposition["notion"] == "Déterminant"
    assert proposition["difficulte"] == "Facile"
    assert proposition["basee_sur_progression"] is True


def test_sans_historique_le_quiz_propose_un_sujet_disponible():
    proposition = _suggestion_quiz(["Physique", "Chimie"], [])

    assert proposition["matiere"] == "Physique"
    assert proposition["notion"] == ""
    assert proposition["difficulte"] == "Moyen"
    assert proposition["basee_sur_progression"] is False


def test_config_quiz_compile_et_ne_demande_plus_de_niveau_manuel():
    template = templates.env.get_template("quiz_config.html")
    source, _, _ = templates.env.loader.get_source(templates.env, "quiz_config.html")

    assert template is not None
    assert 'name="mode_quiz"' in source
    assert 'name="niveau"' not in source
    assert 'value="recommande"' in source
    assert 'value="hasard"' in source
    assert 'value="matiere"' in source
