"""Tests d'intégration du lien entre cours source, quiz ciblé et Tuteur IA."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

from app.models import (
    Document,
    ProgressionNotion,
    RoleUtilisateur,
    SessionTuteur,
    StatutDocument,
    TentativeQuiz,
    TypeDocument,
    Utilisateur,
)
from app.routers import documents_router, quiz_router, tuteur_router


@pytest.fixture
def learning_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def creer_source(session: Session, *, cercle_id=None, fiche_validation_statut="a_verifier"):
    utilisateur = Utilisateur(
        nom="Étudiante parcours",
        telephone="+261340071101",
        mot_de_passe_hash="test-hash",
        role=RoleUtilisateur.ETUDIANT,
        niveau="L1",
    )
    session.add(utilisateur)
    session.commit()
    session.refresh(utilisateur)

    document = Document(
        reference="TEST-PARCOURS-COURS-001",
        titre="Matrices et déterminants",
        matiere="Mathématiques",
        type_document=TypeDocument.COURS,
        annee=2026,
        filiere_id=1,
        uploader_id=utilisateur.id,
        chemin_fichier="/tmp/cours-parcours.pdf",
        statut=StatutDocument.APPROUVE,
        cercle_id=cercle_id,
        fiche_validation_statut=fiche_validation_statut,
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return utilisateur, document


def faux_request():
    return SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))


def test_quiz_documentaire_conserve_la_source_sans_validation_manuelle(learning_engine, monkeypatch):
    with Session(learning_engine) as session:
        utilisateur, document = creer_source(session)
        assert document.fiche_validation_statut == "a_verifier"

        monkeypatch.setattr(
            documents_router, "utilisateur_courant",
            lambda _request, _session: utilisateur,
        )
        monkeypatch.setattr(
            documents_router, "acces_premium_ou_redirection",
            lambda _utilisateur, _session: None,
        )

        @contextmanager
        def faux_fichier(_reference):
            yield Path("/tmp/cours-parcours.pdf")

        questions = [
            {
                "question": "Quelle est la définition d’une matrice identité ?",
                "choix": ["Une matrice particulière", "Un vecteur", "Un scalaire", "Une fonction"],
                "index_bonne_reponse": 0,
                "explication": "Ses coefficients diagonaux valent un.",
                "notion": "Matrice identité",
            },
            {
                "question": "Pourquoi calcule-t-on le déterminant d’une matrice carrée ?",
                "choix": ["Étudier son inversibilité", "Trouver sa couleur", "Mesurer sa longueur", "Calculer sa date"],
                "index_bonne_reponse": 0,
                "explication": "Un déterminant non nul indique l’inversibilité.",
                "notion": "Déterminant",
            },
            {
                "question": "Quand le produit matriciel AB est-il défini ?",
                "choix": ["Quand les dimensions internes coïncident", "Toujours", "Jamais", "Quand A est vide"],
                "index_bonne_reponse": 0,
                "explication": "Les colonnes de A doivent égaler les lignes de B.",
                "notion": "Produit matriciel",
            },
            {
                "question": "Que représente le rang d’une matrice ?",
                "choix": ["La dimension de son espace image", "Son prix", "Son année", "Son format papier"],
                "index_bonne_reponse": 0,
                "explication": "Le rang mesure la dimension de l'espace engendré par ses colonnes.",
                "notion": "Rang",
            },
            {
                "question": "À quoi sert un vecteur propre ?",
                "choix": ["À décrire une direction préservée par une transformation", "À compter les pages", "À nommer une ligne", "À remplacer toute matrice"],
                "index_bonne_reponse": 0,
                "explication": "Un vecteur propre est transformé en un multiple de lui-même.",
                "notion": "Vecteur propre",
            },
        ]
        monkeypatch.setattr(documents_router, "ouvrir_fichier_local", faux_fichier)
        monkeypatch.setattr(documents_router, "extraire_texte", lambda _path: "Contenu pédagogique sur les matrices.")
        monkeypatch.setattr(documents_router.quiz_module, "_questions_vues_recemment", lambda *_args: [])
        monkeypatch.setattr(documents_router, "generer_quiz_depuis_texte", lambda *_args, **_kwargs: questions)
        monkeypatch.setattr(documents_router, "valider_questions", lambda payload, expected_count: payload)
        monkeypatch.setattr(documents_router.ai_queue, "planifier_verification_quiz", lambda _quiz_id: 1)

        response = documents_router.quiz_document(faux_request(), document.id, session)

        assert response.status_code == 303
        assert response.headers["location"].startswith("/quiz/")
        tentative = session.exec(
            select(TentativeQuiz).where(TentativeQuiz.utilisateur_id == utilisateur.id)
        ).first()
        assert tentative is not None
        assert tentative.document_id == document.id
        assert tentative.nb_questions == 5


def test_tuteur_conserve_le_cours_de_la_bibliotheque_generale(
    learning_engine, monkeypatch
):
    with Session(learning_engine) as session:
        utilisateur, document = creer_source(session)
        monkeypatch.setattr(tuteur_router, "utilisateur_courant", lambda *_args: utilisateur)
        monkeypatch.setattr(tuteur_router, "acces_ia_ou_redirection", lambda *_args: None)
        monkeypatch.setattr(tuteur_router, "_contexte_scolaire_tuteur", lambda *_args: None)
        monkeypatch.setattr(tuteur_router, "_document_compatible_au_tuteur", lambda *_args: True)
        monkeypatch.setattr(tuteur_router, "_extrait_document_pertinent", lambda *_args: ("Extrait du cours.", ["section 1"]))
        monkeypatch.setattr(tuteur_router, "limite_depassee", lambda *_args: False)
        monkeypatch.setattr(
            tuteur_router.ai_quiz,
            "generer_reponse_tuteur",
            lambda *_args, **_kwargs: {
                "explication": "Une matrice est un tableau de coefficients.",
                "exemple": "Une matrice identité conserve un vecteur.",
                "exercice": "Calcule un déterminant simple.",
                "correction": "Applique la formule du déterminant.",
                "indice": "Repère les coefficients diagonaux.",
            },
        )
        monkeypatch.setattr(tuteur_router.gamification, "enregistrer_action", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(tuteur_router.ai_queue, "planifier_verification_tuteur", lambda *_args: None)

        # Sans cercle, un cours approuvé de la bibliothèque générale doit être accessible.
        assert tuteur_router._utilisateur_membre_cercle(session, None, utilisateur.id) is True
        response = tuteur_router.demander_tuteur(
            faux_request(),
            question="Aide-moi à comprendre les déterminants.",
            progression_id=None,
            mission_id=None,
            document_id=document.id,
            session=session,
            _csrf=None,
        )

        assert response.status_code == 303
        assert response.headers["location"].startswith("/tuteur/")
        session_tuteur = session.exec(
            select(SessionTuteur).where(SessionTuteur.utilisateur_id == utilisateur.id)
        ).first()
        assert session_tuteur is not None
        assert session_tuteur.document_id == document.id
        assert "Extrait du cours" in session_tuteur.question or session_tuteur.sources_documentaires_json != "[]"


def test_quiz_cible_propage_la_source_et_refuse_un_document_de_cercle_non_autorise(
    learning_engine, monkeypatch
):
    with Session(learning_engine) as session:
        utilisateur, document = creer_source(session)
        progression = ProgressionNotion(
            utilisateur_id=utilisateur.id,
            matiere="Mathématiques",
            niveau="L1",
            notion="Déterminant",
            nb_questions=5,
            nb_erreurs=3,
            score_maitrise=35,
            maitrise_confirmee=False,
        )
        session.add(progression)
        session.commit()
        session.refresh(progression)

        monkeypatch.setattr(quiz_router, "utilisateur_courant", lambda *_args: utilisateur)
        monkeypatch.setattr(quiz_router, "acces_ia_ou_redirection", lambda *_args: None)
        monkeypatch.setattr(quiz_router, "_contexte_scolaire_quiz", lambda *_args: None)
        monkeypatch.setattr(quiz_router, "limite_depassee", lambda *_args: False)
        monkeypatch.setattr(quiz_router.quiz_module, "revision_due", lambda *_args: False)
        monkeypatch.setattr(quiz_router.quiz_module, "besoin_preuve_maitrise", lambda *_args: False)

        def creer_tentative_fake(session_db, user, matiere, niveau, notion, **kwargs):
            tentative = TentativeQuiz(
                utilisateur_id=user.id,
                matiere=matiere,
                niveau=niveau,
                difficulte="Moyen",
                nb_questions=1,
                questions_json='[{"question":"Question ?","choix":["A","B"],"index_bonne_reponse":0}]',
            )
            session_db.add(tentative)
            session_db.commit()
            session_db.refresh(tentative)
            return tentative

        monkeypatch.setattr(quiz_router.quiz_module, "creer_tentative_ciblee", creer_tentative_fake)
        monkeypatch.setattr(quiz_router.ai_queue, "planifier_verification_quiz", lambda *_args: 1)

        response = quiz_router.generer_quiz_cible(
            faux_request(),
            progression_id=progression.id,
            mission_id=None,
            document_id=document.id,
            session=session,
            _csrf=None,
        )
        assert response.status_code == 303
        tentative = session.exec(
            select(TentativeQuiz).where(TentativeQuiz.utilisateur_id == utilisateur.id)
            .order_by(TentativeQuiz.id.desc())
        ).first()
        assert tentative.document_id == document.id

        # Même un cours approuvé ne doit pas servir de source à un membre hors de son cercle.
        document.cercle_id = 9001
        session.add(document)
        session.commit()
        compteur_avant = len(session.exec(
            select(TentativeQuiz).where(TentativeQuiz.utilisateur_id == utilisateur.id)
        ).all())

        response = quiz_router.generer_quiz_cible(
            faux_request(),
            progression_id=progression.id,
            mission_id=None,
            document_id=document.id,
            session=session,
            _csrf=None,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/mes-revisions?erreur=source_indisponible"
        compteur_apres = len(session.exec(
            select(TentativeQuiz).where(TentativeQuiz.utilisateur_id == utilisateur.id)
        ).all())
        assert compteur_apres == compteur_avant


def test_templates_exposent_les_etapes_du_parcours():
    from pathlib import Path

    racine = Path(__file__).resolve().parents[1] / "app" / "templates"
    fiche = (racine / "document_revision.html").read_text(encoding="utf-8")
    resultat = (racine / "quiz_resultat.html").read_text(encoding="utf-8")
    tuteur = (racine / "tuteur_reponse.html").read_text(encoding="utf-8")

    assert "Continuer mon parcours d'apprentissage" in fiche
    assert "/documents/{{ document.id }}/quiz" in fiche
    assert 'name="document_id" value="{{ document.id }}"' in fiche
    assert 'name="document_id" value="{{ tentative.document_id }}"' in resultat
    assert "Retour au cours source" in resultat
    assert 'name="document_id" value="{{ session_tuteur.document_id }}"' in tuteur
    assert "/documents/{{ session_tuteur.document_id }}/apprendre" in tuteur
