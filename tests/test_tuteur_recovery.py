from datetime import datetime, timedelta

from sqlmodel import Session, SQLModel, create_engine

from app import ai_quiz
from app.models import SessionTuteur, Utilisateur


def test_reparation_tuteur_reprend_une_session_trop_longtemps_en_attente(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ai_quiz, "engine", engine)

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
        ai_quiz,
        "verifier_session_tuteur_en_arriere_plan",
        lambda session_id: appelees.append(session_id),
    )

    assert ai_quiz.reparer_verifications_tuteur_en_attente() == 1
    assert appelees == [ancienne_id]


def test_reparation_tuteur_n_intervient_pas_sur_une_session_recente(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ai_quiz, "engine", engine)

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
