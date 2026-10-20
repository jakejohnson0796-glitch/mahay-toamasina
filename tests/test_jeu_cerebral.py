import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import sqlite
from jinja2 import Environment, FileSystemLoader
from sqlmodel import Session, SQLModel, create_engine

from app import jeu_cerebral
from app.models import Document, JeuCerebralSession, MembreCercle, StatutDocument, Utilisateur
from app.quiz_validation import valider_questions
from app.routers import jeu_cerebral_router
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
    assert profil["notions_a_renforcer"] == []
    assert profil["notions_bien_reussies"] == []


def test_profil_compte_toutes_les_sessions_mais_ne_garde_que_cinq_scores_recents():
    sessions = [
        SimpleNamespace(score=40 + index, theme_id="calcul")
        for index in range(8)
    ]
    profil = jeu_cerebral.profil_pour_ia(sessions)

    assert profil["sessions_terminees"] == 8
    assert len(profil["scores_recents"]) == 5
    assert profil["scores_recents"] == [40, 41, 42, 43, 44]


def test_progression_par_notion_agrege_plusieurs_sessions_sans_surinterpreter_un_essai():
    def partie(theme, notions, reponses, langue="fr"):
        questions = [
            {
                "question": "Question de suivi",
                "choix": ["Non", "Oui"],
                "index_bonne_reponse": 1,
                "notion": notion,
            }
            for notion in notions
        ]
        etat = {"ordre": list(range(len(questions))), "reponses": reponses}
        return SimpleNamespace(
            theme_id=theme,
            langue=langue,
            score=0,
            date_fin="completed",
            questions_json=json.dumps(questions, ensure_ascii=False),
            reponses_json=json.dumps(etat, ensure_ascii=False),
        )

    # L'ordre fourni est du plus récent au plus ancien.
    session_inachevee = partie("calcul", ["Calcul mental"], [1])
    session_inachevee.date_fin = None
    sessions = [
        session_inachevee,
        partie("calcul", ["Calcul mental"], [0]),
        partie("calcul", ["Calcul mental", "Logique"], [0, 1]),
        partie("calcul", ["Calcul mental", "Logique", "Observation"], [1, 1, 0]),
        SimpleNamespace(theme_id="calcul", langue="fr", questions_json="{bad", reponses_json="{}"),
    ]

    progression = jeu_cerebral.progression_sur_plusieurs_sessions(sessions)

    assert progression["sessions_analysees"] == 3
    assert progression["reponses_analysees"] == 6
    assert progression["notions_suivies"] == 3
    assert progression["a_renforcer"][0]["notion"] == "Calcul mental"
    assert progression["a_renforcer"][0]["essais"] == 3
    assert progression["a_renforcer"][0]["bonnes_reponses"] == 1
    assert progression["a_renforcer"][0]["taux_reussite"] == 33
    assert progression["a_renforcer"][0]["dernier_resultat"] is False
    assert progression["bien_reussies"][0]["notion"] == "Logique"
    assert progression["bien_reussies"][0]["taux_reussite"] == 100
    assert progression["a_observer"][0]["notion"] == "Observation"
    assert progression["a_observer"][0]["essais"] == 1


def test_progression_par_notion_filtre_la_langue_pour_personnaliser_la_banque():
    def partie(notion, reponse, langue):
        question = {"question": "Question", "choix": ["Non", "Oui"], "index_bonne_reponse": 1, "notion": notion}
        return SimpleNamespace(
            theme_id="logique",
            langue=langue,
            date_fin="completed",
            questions_json=json.dumps([question], ensure_ascii=False),
            reponses_json=json.dumps({"ordre": [0], "reponses": [reponse]}, ensure_ascii=False),
        )

    progression = jeu_cerebral.progression_sur_plusieurs_sessions(
        [partie("Logique", 0, "fr"), partie("Lojika", 1, "mg")],
        langue="fr",
    )

    assert progression["sessions_analysees"] == 1
    assert progression["reponses_analysees"] == 1
    assert progression["a_observer"][0]["notion"] == "Logique"
    assert progression["a_observer"][0]["taux_reussite"] == 0


def test_ressource_recommandee_exige_un_titre_ou_une_matiere_explicitement_pertinents():
    notion = {"notion": "Calcul mental et estimation", "essais": 3, "taux_reussite": 33}
    documents = [
        SimpleNamespace(
            id=1,
            titre="Introduction générale",
            matiere="Mathématiques",
            type_document="cours",
            annee=2025,
            reference="REF-GENERAL",
        ),
        SimpleNamespace(
            id=2,
            titre="Exercices de calcul mental",
            matiere="Mathématiques",
            type_document="fiche",
            annee=2024,
            reference="REF-CALCUL",
        ),
    ]

    suggestions = jeu_cerebral.trouver_ressources_pour_notion([notion], documents)

    assert len(suggestions) == 1
    assert suggestions[0]["document_id"] == 2
    assert suggestions[0]["notion"] == "Calcul mental et estimation"
    assert suggestions[0]["reference"] == "REF-CALCUL"


def test_recommandation_ressource_ne_devine_pas_une_correspondance_vague():
    notions = [
        {"notion": "Observation et attention", "essais": 3, "taux_reussite": 0},
        {"notion": "Une notion inconnue", "essais": 2, "taux_reussite": 50},
    ]
    documents = [
        SimpleNamespace(
            id=8,
            titre="Cours général de mathématiques",
            matiere="Mathématiques",
            type_document="cours",
            annee=2025,
            reference="REF-MATH",
        )
    ]

    assert jeu_cerebral.trouver_ressources_pour_notion(notions, documents) == []


def test_ressources_recommandees_sont_filtrees_par_filiere_statut_et_acces_cercle(monkeypatch):
    from app.routers.jeu_cerebral_router import _ressources_pour_progression

    class Rows:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class QuerySession:
        def __init__(self, documents):
            self.documents = documents
            self.sql = []

        def exec(self, statement):
            rendered = str(statement.compile(
                dialect=sqlite.dialect(),
                compile_kwargs={"literal_binds": True},
            ))
            self.sql.append(rendered)
            if "membrecercle" in rendered.lower():
                return Rows([7])
            if "from document" in rendered.lower():
                return Rows(self.documents)
            return Rows([])

    document = SimpleNamespace(
        id=12,
        titre="Exercices de calcul mental",
        matiere="Mathématiques",
        statut=StatutDocument.APPROUVE,
        filiere_id=4,
        cercle_id=7,
        type_document="fiche",
        annee=2024,
        reference="REF-12",
    )
    fake_session = QuerySession([document])
    utilisateur = SimpleNamespace(id=3, filiere_id=4)
    progression = {
        "a_renforcer": [
            {"notion": "Calcul mental et estimation", "essais": 3, "taux_reussite": 33}
        ]
    }

    suggestions = _ressources_pour_progression(fake_session, utilisateur, progression)

    assert suggestions[0]["document_id"] == 12
    requete = next(sql for sql in fake_session.sql if "from document" in sql.lower())
    assert "document.statut = 'approuve'" in requete
    assert "document.filiere_id = 4" in requete
    assert "document.cercle_id IS NULL" in requete
    assert "document.cercle_id IN (7)" in requete


def test_parcours_route_complet_demarrage_reponses_enregistrement_et_bilan(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            utilisateur = Utilisateur(
                nom="Test Jeu",
                telephone="690000991",
                mot_de_passe_hash="hash",
            )
            db.add(utilisateur)
            db.commit()
            db.refresh(utilisateur)

            monkeypatch.setattr(
                jeu_cerebral_router,
                "utilisateur_courant",
                lambda _request, _session: utilisateur,
            )
            monkeypatch.setattr(jeu_cerebral_router, "limite_depassee", lambda *_args, **_kwargs: False)
            # Simule une IA non disponible : le flux doit utiliser la banque locale.
            monkeypatch.setattr(
                jeu_cerebral_router,
                "acces_ia_ou_redirection",
                lambda *_args, **_kwargs: "/abonnement",
            )
            questions = _questions_test()
            monkeypatch.setattr(
                jeu_cerebral_router.jeu_cerebral,
                "generer_banque_questions",
                lambda *_args, **_kwargs: (questions, "local"),
            )
            monkeypatch.setattr(
                jeu_cerebral_router.gamification,
                "enregistrer_action",
                lambda *_args, **_kwargs: None,
            )
            monkeypatch.setattr(
                jeu_cerebral_router.templates,
                "TemplateResponse",
                lambda _request, template_name, context: SimpleNamespace(
                    template_name=template_name,
                    context=context,
                ),
            )
            request = SimpleNamespace(
                client=SimpleNamespace(host="127.0.0.1"),
                query_params={},
            )

            demarrage = jeu_cerebral_router.demarrer_jeu_cerebral(
                request,
                theme="calcul",
                langue="fr",
                chronometre="1",
                session=db,
                _csrf=None,
            )
            assert demarrage.status_code == 303
            partie_id = int(demarrage.headers["location"].rsplit("/", 1)[1])
            partie = db.get(JeuCerebralSession, partie_id)
            assert partie is not None
            assert partie.date_fin is None
            assert partie.source_generation == "local"
            assert jeu_cerebral.lire_etat(partie.reponses_json)["chrono_actif"] is True

            for position in range(jeu_cerebral.NB_QUESTIONS_SESSION):
                ecran = jeu_cerebral_router.page_session_jeu_cerebral(
                    request,
                    partie_id=partie_id,
                    session=db,
                )
                assert ecran.template_name == "jeu_cerebral_session.html"
                partie = db.get(JeuCerebralSession, partie_id)
                etat = jeu_cerebral.lire_etat(partie.reponses_json)
                active_index = etat["ordre"][-1]
                reponse_http = jeu_cerebral_router.repondre_jeu_cerebral(
                    request,
                    partie_id=partie_id,
                    index_question=active_index,
                    reponse=0,
                    session=db,
                    _csrf=None,
                )
                assert reponse_http.status_code == 303
                if position < jeu_cerebral.NB_QUESTIONS_SESSION - 1:
                    assert reponse_http.headers["location"] == f"/jeu-cerebral/{partie_id}"
                else:
                    assert reponse_http.headers["location"] == f"/jeu-cerebral/{partie_id}/resultat"

            db.refresh(partie)
            assert partie.date_fin is not None
            assert partie.score == 100
            assert partie.bonnes_reponses == jeu_cerebral.NB_QUESTIONS_SESSION

            bilan = jeu_cerebral_router.resultat_jeu_cerebral(
                request,
                partie_id=partie_id,
                session=db,
            )
            assert bilan.template_name == "jeu_cerebral_resultat.html"
            assert len(bilan.context["corrections"]) == jeu_cerebral.NB_QUESTIONS_SESSION
            assert bilan.context["progression_notion"]["sessions_analysees"] == 1
            assert bilan.context["ressources_recommandees"] == []
    finally:
        SQLModel.metadata.drop_all(engine)
        engine.dispose()


def test_page_jeu_et_templates_compilent():
    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"))
    for template in (
        "jeu_cerebral.html",
        "jeu_cerebral_session.html",
        "jeu_cerebral_resultat.html",
    ):
        assert env.get_template(template) is not None


def test_interface_affiche_la_progression_par_notion_sur_plusieurs_sessions():
    accueil = (ROOT / "app" / "templates" / "jeu_cerebral.html").read_text(encoding="utf-8")
    bilan = (ROOT / "app" / "templates" / "jeu_cerebral_resultat.html").read_text(encoding="utf-8")

    assert 'id="jeu-progression-title"' in accueil
    assert "progression_notion.a_renforcer" in accueil
    assert "progression_notion.bien_reussies" in accueil
    assert "progression_notion.a_observer" in accueil
    assert 'id="jeu-progression-historique-title"' in bilan
    assert "progression_notion.sessions_analysees" in bilan
    assert "progression_notion.a_renforcer" in bilan
    assert "plusieurs réponses observées" in bilan


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
