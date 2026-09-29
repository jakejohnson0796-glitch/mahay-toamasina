from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine

from app import ai_queue
from app.models import StatutTacheIA, TacheIA, TentativeQuiz, Utilisateur


def test_file_ia_planification_idempotente(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ai_queue, "engine", engine)

    with Session(engine) as session:
        utilisateur = Utilisateur(
            nom="Test",
            telephone="690000000",
            mot_de_passe_hash="hash",
        )
        session.add(utilisateur)
        session.commit()
        session.refresh(utilisateur)

        tentative = TentativeQuiz(
            utilisateur_id=utilisateur.id,
            matiere="Mathematiques",
            niveau="L1",
            difficulte="Moyen",
            nb_questions=1,
            questions_json="[]",
        )
        session.add(tentative)
        session.commit()
        session.refresh(tentative)

        first = ai_queue.planifier_verification_quiz(tentative.id)
        second = ai_queue.planifier_verification_quiz(tentative.id)

        assert first == second

        tache = session.get(TacheIA, first)
        assert tache is not None
        assert tache.statut == StatutTacheIA.EN_ATTENTE
        assert tache.tentative_quiz_id == tentative.id


def test_file_ia_prend_et_termine_une_tache(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ai_queue, "engine", engine)

    with Session(engine) as session:
        utilisateur = Utilisateur(
            nom="Test2",
            telephone="690000001",
            mot_de_passe_hash="hash",
        )
        session.add(utilisateur)
        session.commit()
        session.refresh(utilisateur)

        tentative = TentativeQuiz(
            utilisateur_id=utilisateur.id,
            matiere="Physique",
            niveau="L1",
            difficulte="Moyen",
            nb_questions=1,
            questions_json="[]",
        )
        session.add(tentative)
        session.commit()
        session.refresh(tentative)

    tache_id = ai_queue.planifier_verification_quiz(tentative.id)
    tache = ai_queue.prendre_tache()

    assert tache is not None
    assert tache.id == tache_id
    assert tache.statut == StatutTacheIA.EN_COURS
    assert tache.nombre_essais == 1

    ai_queue.terminer_tache(tache.id)

    with Session(engine) as session:
        final = session.get(TacheIA, tache.id)
        assert final is not None
        assert final.statut == StatutTacheIA.TERMINEE
        assert final.terminee_le is not None
