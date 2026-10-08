from datetime import datetime, timedelta

from sqlmodel import Session, SQLModel, create_engine

from app import ai_queue, ai_quiz
from app.models import ProgressionNotion, SessionTuteur, Utilisateur


def test_reparation_tuteur_reprend_une_session_trop_longtemps_en_attente(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr("app.database.engine", engine)

    with Session(engine) as session:
        utilisateur = Utilisateur(
            nom="Tutor Recovery",
            telephone="690000100",
            mot_de_passe_hash="hash",
        )
        session.add(utilisateur)
        session.commit()
        session.refresh(utilisateur)

        ancienne = SessionTuteur(
            utilisateur_id=utilisateur.id,
            notion="Dérivées",
            question="Explique-moi la dérivée.",
            explication="Réponse initiale.",
            exemple="Exemple.",
            exercice="Exercice.",
            correction="Correction.",
            statut_verification_ia="en_attente",
            date_creation=datetime.utcnow() - timedelta(minutes=3),
        )
        session.add(ancienne)
        session.commit()
        session.refresh(ancienne)
        ancienne_id = ancienne.id

    appelees = []
    monkeypatch.setattr(
        ai_queue,
        "planifier_verification_tuteur",
        lambda session_id: appelees.append(session_id) or session_id,
    )

    assert ai_quiz.reparer_verifications_tuteur_en_attente() == 1
    assert appelees == [ancienne_id]


def test_reparation_tuteur_n_intervient_pas_sur_une_session_recente(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr("app.database.engine", engine)

    with Session(engine) as session:
        utilisateur = Utilisateur(
            nom="Tutor Recent",
            telephone="690000101",
            mot_de_passe_hash="hash",
        )
        session.add(utilisateur)
        session.commit()
        session.refresh(utilisateur)

        recente = SessionTuteur(
            utilisateur_id=utilisateur.id,
            notion="Algèbre",
            question="Explique cette notion.",
            explication="Réponse.",
            exemple="Exemple.",
            exercice="Exercice.",
            correction="Correction.",
            statut_verification_ia="en_attente",
            date_creation=datetime.utcnow(),
        )
        session.add(recente)
        session.commit()

    appelees = []
    monkeypatch.setattr(
        ai_quiz,
        "verifier_session_tuteur_en_arriere_plan",
        lambda session_id: appelees.append(session_id),
    )

    assert ai_quiz.reparer_verifications_tuteur_en_attente() == 0
    assert appelees == []


def test_reparation_tuteur_reprend_une_verification_en_cours_orpheline(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr("app.database.engine", engine)

    with Session(engine) as session:
        utilisateur = Utilisateur(
            nom="Tutor Orphelin",
            telephone="690000102",
            mot_de_passe_hash="hash",
        )
        session.add(utilisateur)
        session.commit()
        session.refresh(utilisateur)

        ancienne = SessionTuteur(
            utilisateur_id=utilisateur.id,
            notion="Matrices",
            question="Calcule ce déterminant.",
            explication="Réponse.",
            exemple="Exemple.",
            exercice="Exercice.",
            correction="Correction.",
            statut_verification_ia="en_cours",
            date_creation=datetime.utcnow() - timedelta(minutes=10),
            date_verification_ia=datetime.utcnow() - timedelta(minutes=10),
        )
        session.add(ancienne)
        session.commit()
        session.refresh(ancienne)
        ancienne_id = ancienne.id

    appelees = []
    monkeypatch.setattr(
        ai_quiz,
        "verifier_session_tuteur_en_arriere_plan",
        lambda session_id: appelees.append(session_id),
    )

    assert ai_quiz.reparer_verifications_tuteur_en_attente() == 1
    assert appelees == [ancienne_id]


def test_reparation_tuteur_ne_reprend_pas_une_verification_en_cours_recente(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr("app.database.engine", engine)

    with Session(engine) as session:
        utilisateur = Utilisateur(
            nom="Tutor En cours",
            telephone="690000103",
            mot_de_passe_hash="hash",
        )
        session.add(utilisateur)
        session.commit()
        session.refresh(utilisateur)

        recente = SessionTuteur(
            utilisateur_id=utilisateur.id,
            notion="Physique",
            question="Explique la loi d'Ohm.",
            explication="Réponse.",
            exemple="Exemple.",
            exercice="Exercice.",
            correction="Correction.",
            statut_verification_ia="en_cours",
            date_creation=datetime.utcnow() - timedelta(minutes=1),
            date_verification_ia=datetime.utcnow(),
        )
        session.add(recente)
        session.commit()

    appelees = []
    monkeypatch.setattr(
        ai_quiz,
        "verifier_session_tuteur_en_arriere_plan",
        lambda session_id: appelees.append(session_id),
    )

    assert ai_quiz.reparer_verifications_tuteur_en_attente() == 0
    assert appelees == []


def test_verification_tuteur_charge_la_matiere_de_la_progression(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr("app.database.engine", engine)

    with Session(engine) as session:
        utilisateur = Utilisateur(
            nom="Tutor Progression",
            telephone="690000104",
            mot_de_passe_hash="hash",
        )
        session.add(utilisateur)
        session.commit()
        session.refresh(utilisateur)

        progression = ProgressionNotion(
            utilisateur_id=utilisateur.id,
            matiere="Mathématiques",
            notion="Déterminant d'ordre 2",
            niveau="L1",
            score_maitrise=42,
            nb_questions=4,
            nb_reussites=2,
            nb_erreurs=2,
        )
        session.add(progression)
        session.commit()
        session.refresh(progression)

        session_tuteur = SessionTuteur(
            utilisateur_id=utilisateur.id,
            notion=progression.notion,
            progression_id=progression.id,
            question="Calcule le déterminant de cette matrice.",
            explication="Réponse initiale.",
            exemple="Exemple.",
            exercice="Exercice.",
            correction="Correction.",
        )
        session.add(session_tuteur)
        session.commit()
        session.refresh(session_tuteur)
        session_tuteur_id = session_tuteur.id

    appels = []

    def _verification_fictive(initiale, *, question, notion, matiere, strategie):
        appels.append(
            {
                "question": question,
                "notion": notion,
                "matiere": matiere,
                "strategie": strategie,
                "initiale": initiale,
            }
        )
        return {
            "explication": "Réponse vérifiée.",
            "exemple": initiale["exemple"],
            "exercice": initiale["exercice"],
            "correction": initiale["correction"],
            "_statut_verification": "terminee",
        }

    monkeypatch.setattr(
        ai_quiz,
        "verifier_reponse_tuteur_structuree",
        _verification_fictive,
    )

    ai_quiz.verifier_session_tuteur_en_arriere_plan(session_tuteur_id)

    assert appels == [
        {
            "question": "Calcule le déterminant de cette matrice.",
            "notion": "Déterminant d'ordre 2",
            "matiere": "Mathématiques",
            "strategie": "legere",
            "initiale": {
                "explication": "Réponse initiale.",
                "exemple": "Exemple.",
                "exercice": "Exercice.",
                "correction": "Correction.",
            },
        }
    ]

    with Session(engine) as session:
        resultat = session.get(SessionTuteur, session_tuteur_id)
        assert resultat is not None
        assert resultat.statut_verification_ia == "terminee"
        assert resultat.explication == "Réponse vérifiée."
