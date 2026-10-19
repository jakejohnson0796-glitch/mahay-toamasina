from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import Environment, FileSystemLoader
from sqlmodel import Session, SQLModel, create_engine

from app import jeu_cerebral
from app.models import JeuCerebralSession, Utilisateur
from app.quiz_validation import valider_questions
from app.routers.jeu_cerebral_router import _partie_du_proprietaire


ROOT = Path(__file__).resolve().parents[1]


def _questions_test(difficultes=None):
    difficultes = difficultes or ["Facile", "Facile", "Moyen", "Moyen", "Difficile"]
    return [
        {
            "question": f"Question de test numéro {index + 1} ?",
            "choix": ["Réponse A", "Réponse B", "Réponse C", "Réponse D"],
            "index_bonne_reponse": 0,
            "explication": "La première réponse est la bonne dans ce test.",
            "notion": f"Compétence {index + 1}",
            "difficulte": difficulte,
        }
        for index, difficulte in enumerate(difficultes)
    ]


def test_tous_les_themes_ont_une_banque_locale_valide_et_suffisante():
    assert set(jeu_cerebral.BANQUE_LOCALE) == set(jeu_cerebral.THEMES_PAR_ID)
    for theme in jeu_cerebral.THEMES:
        questions = jeu_cerebral.BANQUE_LOCALE[theme["id"]]
        assert len(questions) >= jeu_cerebral.NB_QUESTIONS_SESSION
        assert {question["difficulte"] for question in questions} == set(jeu_cerebral.DIFFICULTES)
        valider_questions(questions, expected_count=len(questions), strict_coherence=True)


def test_mode_local_fournit_des_questions_en_francais_et_en_malagasy(monkeypatch):
    francais, source_fr = jeu_cerebral.generer_banque_questions(
        "logique", "fr", {}, utiliser_ia=False
    )
    malagasy, source_mg = jeu_cerebral.generer_banque_questions(
        "logique", "mg", {}, utiliser_ia=False
    )

    assert source_fr == source_mg == "local"
    assert "Quatre boras" not in francais[0]["question"]
    assert "Bora rehetra" in malagasy[0]["question"]
    assert "question_mg" not in malagasy[0]
    assert malagasy[0]["choix"] != francais[0]["choix"]


def test_indisponibilite_ia_revient_au_mode_local(monkeypatch):
    def indisponible():
        raise RuntimeError("IA indisponible")

    monkeypatch.setattr(jeu_cerebral.ai_quiz, "_obtenir_client", indisponible)
    questions, source = jeu_cerebral.generer_banque_questions(
        "calcul", "fr", {"difficulte_depart": "Moyen"}, utiliser_ia=True
    )
    assert source == "local"
    assert len(questions) >= jeu_cerebral.NB_QUESTIONS_SESSION


def test_theme_invalide_ne_peut_pas_injecter_un_libelle():
    assert jeu_cerebral.obtenir_theme("calcul")["id"] == "calcul"
    assert jeu_cerebral.obtenir_theme("../../admin")["id"] == "logique"


def test_deux_bonnes_reponses_consecutives_peuvent_eleveer_le_niveau():
    questions = _questions_test(["Facile", "Facile", "Moyen", "Moyen", "Difficile"])
    etat = jeu_cerebral.etat_initial(questions, "Facile")
    premier = etat["ordre"][-1]
    etat, correcte, suivant = jeu_cerebral.enregistrer_reponse(
        questions, etat, premier, 0
    )
    assert correcte is True
    assert suivant is not None
    assert questions[suivant]["difficulte"] == "Facile"

    etat, correcte, suivant = jeu_cerebral.enregistrer_reponse(
        questions, etat, suivant, 0
    )
    assert correcte is True
    assert etat["cible_difficulte"] == "Moyen"
    assert suivant is not None
    assert questions[suivant]["difficulte"] == "Moyen"


def test_mauvaise_reponse_abaisse_la_cible_et_recommande_sans_juger():
    questions = _questions_test(["Difficile", "Difficile", "Moyen", "Facile", "Moyen"])
    etat = jeu_cerebral.etat_initial(questions, "Difficile")
    courant = etat["ordre"][-1]

    etat, correcte, suivant = jeu_cerebral.enregistrer_reponse(
        questions, etat, courant, 1, langue="fr"
    )

    assert correcte is False
    assert etat["cible_difficulte"] == "Moyen"
    assert etat["dernier_feedback"]["message"].startswith("Pas de souci")
    assert suivant is not None
    assert questions[suivant]["difficulte"] == "Moyen"


def test_ne_peut_pas_repondre_deux_fois_ni_a_une_question_inactive():
    questions = _questions_test()
    etat = jeu_cerebral.etat_initial(questions, "Facile")
    courant = etat["ordre"][-1]
    etat, _, suivant = jeu_cerebral.enregistrer_reponse(questions, etat, courant, 0)
    with pytest.raises(jeu_cerebral.QuizValidationError):
        jeu_cerebral.enregistrer_reponse(questions, etat, courant, 0)
    autre = next(i for i in range(len(questions)) if i not in etat["ordre"])
    with pytest.raises(jeu_cerebral.QuizValidationError):
        jeu_cerebral.enregistrer_reponse(questions, etat, autre, 0)


def test_session_se_termine_apres_cinq_questions_distinctes_et_compte_correctement():
    questions = _questions_test()
    etat = jeu_cerebral.etat_initial(questions, "Facile")
    for numero in range(jeu_cerebral.NB_QUESTIONS_SESSION):
        courant = etat["ordre"][-1]
        # Un seul faux choix permet de vérifier aussi le retour de difficulté.
        reponse = 0 if numero < 4 else 1
        etat, _, suivant = jeu_cerebral.enregistrer_reponse(
            questions, etat, courant, reponse
        )
        if numero < jeu_cerebral.NB_QUESTIONS_SESSION - 1:
            assert suivant is not None
    assert etat["termine"] is True
    ordre = etat["ordre"]
    assert len(ordre) == jeu_cerebral.NB_QUESTIONS_SESSION
    assert len(set(ordre)) == jeu_cerebral.NB_QUESTIONS_SESSION
    recommandation = jeu_cerebral.construire_recommandation("logique", questions, etat)
    assert recommandation["total"] == 5
    assert recommandation["bonnes_reponses"] == 4
    assert recommandation["score"] == 80
    assert recommandation["titre"].startswith("Très belle session")
    assert recommandation["a_explorer"]


def test_recommandation_malagasy_contient_un_message_encourageant():
    questions = _questions_test()
    etat = jeu_cerebral.etat_initial(questions, "Facile")
    etat["langue"] = "mg"
    for numero in range(jeu_cerebral.NB_QUESTIONS_SESSION):
        courant = etat["ordre"][-1]
        etat, _, _ = jeu_cerebral.enregistrer_reponse(
            questions, etat, courant, 1, langue="mg"
        )
    bilan = jeu_cerebral.construire_recommandation("logique", questions, etat)
    assert bilan["score"] == 0
    assert "Tsy mamaritra" in bilan["message_mg"]
    assert bilan["conseil_mg"]


def test_profil_ne_essaie_pas_de_mesurer_l_intelligence_et_calibre_la_difficulte():
    sessions = [
        SimpleNamespace(score=90, theme_id="calcul"),
        SimpleNamespace(score=85, theme_id="calcul"),
        SimpleNamespace(score=82, theme_id="logique"),
    ]
    profil = jeu_cerebral.profil_pour_ia(sessions)
    assert profil["sessions_terminees"] == 3
    assert profil["moyenne_recente"] == 86
    assert profil["difficulte_depart"] == "Difficile"
    assert profil["meilleure_piste"] == "calcul"


def test_page_jeu_et_templates_compilent():
    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"))
    for template in (
        "jeu_cerebral.html",
        "jeu_cerebral_session.html",
        "jeu_cerebral_resultat.html",
    ):
        assert env.get_template(template) is not None


def test_partie_est_visible_uniquement_par_son_proprietaire():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            proprietaire = Utilisateur(
                nom="Etudiant Un",
                telephone="690000101",
                mot_de_passe_hash="hash",
            )
            autre = Utilisateur(
                nom="Etudiant Deux",
                telephone="690000102",
                mot_de_passe_hash="hash",
            )
            session.add(proprietaire)
            session.add(autre)
            session.commit()
            session.refresh(proprietaire)
            session.refresh(autre)
            partie = JeuCerebralSession(
                utilisateur_id=proprietaire.id,
                theme_id="logique",
                langue="fr",
                source_generation="local",
                difficulte_initiale="Moyen",
                nb_questions=5,
                questions_json="[]",
                reponses_json="{}",
            )
            session.add(partie)
            session.commit()
            session.refresh(partie)

            assert _partie_du_proprietaire(session, partie.id, proprietaire.id) is not None
            assert _partie_du_proprietaire(session, partie.id, autre.id) is None
            assert _partie_du_proprietaire(session, 999_999, proprietaire.id) is None
    finally:
        engine.dispose()



def test_interface_accueil_du_jeu_utilise_de_vraies_cartes_accessibles_et_responsives():
    source = (ROOT / "app" / "templates" / "jeu_cerebral.html").read_text(encoding="utf-8")

    # Régression constatée sur capture : un span de carte inline fragmentait
    # la bordure et le sélecteur générique stylait l'emoji comme une description.
    assert ".jeu-theme-card{display:flex" in source
    assert ".jeu-theme-card span{display:block" not in source
    assert 'class="jeu-theme-description"' in source
    assert '<fieldset class="jeu-theme-grid"' in source
    assert ".jeu-theme-option:focus-within .jeu-theme-card" in source
    assert "@media(max-width:900px)" in source
    assert "@media(max-width:440px)" in source
    assert "prefers-reduced-motion:reduce" in source
    assert 'name="chronometre" value="1"' in source
    assert 'id="jeu-reduire-animations"' in source
    assert "jeu-cerebral.js?v=" in source



def test_les_formules_du_jeu_cerebral_emploient_le_rendu_scientifique():
    session_template = (
        ROOT / "app" / "templates" / "jeu_cerebral_session.html"
    ).read_text(encoding="utf-8")
    result_template = (
        ROOT / "app" / "templates" / "jeu_cerebral_resultat.html"
    ).read_text(encoding="utf-8")
    base_template = (
        ROOT / "app" / "templates" / "base.html"
    ).read_text(encoding="utf-8")

    # Une question, ses options et ses corrections peuvent toutes contenir du LaTeX.
    assert 'id="question-du-jeu" data-rendu' in session_template
    assert '<span data-no-translate data-rendu>{{ choix }}</span>' in session_template
    assert '<p data-no-translate data-rendu>{{ retour.explication }}</p>' in session_template
    assert '<span data-no-translate data-rendu>{{ correction.question }}</span>' in result_template
    assert 'data-rendu>{{ correction.explication }}' in result_template

    # Le renderer/KaTeX était auparavant chargé uniquement sur Quiz IA et Tuteur IA.
    assert 'request.url.path.startswith("/jeu-cerebral")' in base_template
    assert 'src="/static/js/rendu_ia.js' in base_template
    assert 'src="/static/js/charger-dependances-ia.js' in base_template



def test_illustrations_du_jeu_cerebral_sont_locales_et_utilisees():
    accueil = (ROOT / "app" / "templates" / "jeu_cerebral.html").read_text(encoding="utf-8")
    session = (ROOT / "app" / "templates" / "jeu_cerebral_session.html").read_text(encoding="utf-8")
    resultat = (ROOT / "app" / "templates" / "jeu_cerebral_resultat.html").read_text(encoding="utf-8")
    assets = ROOT / "app" / "static" / "images" / "jeu-cerebral"

    assert "brain-hero.webp" in accueil
    assert "illustrations/calcul.svg" in accueil
    assert "mascotte-pink.webp" in session
    assert "trophy.webp" in resultat

    for nom in ("brain-hero.webp", "math-visual.webp", "mascotte-pink.webp", "trophy.webp"):
        fichier = assets / nom
        assert fichier.is_file(), f"Illustration manquante : {nom}"
        assert 0 < fichier.stat().st_size < 100_000, f"Illustration trop volumineuse : {nom}"

    assert 'alt=""' in accueil
    assert "prefers-reduced-motion:reduce" in accueil
    assert 'name="chronometre" value="1"' in accueil
    assert "jeu-pause-toggle" in session
    assert "jeu-chrono-panel" in session
    assert "illustrations/logique.svg" in session
    for nom in ("logique.svg", "calcul.svg", "suites.svg", "langage.svg", "observation.svg"):
        fichier = assets / "illustrations" / nom
        assert fichier.is_file(), f"Illustration thématique manquante : {nom}"
        assert 0 < fichier.stat().st_size < 20_000, f"Illustration SVG trop volumineuse : {nom}"
    assert "sessionStorage" in (ROOT / "app" / "static" / "js" / "jeu-cerebral.js").read_text(encoding="utf-8")
    assert "loading=\"lazy\"" in session
