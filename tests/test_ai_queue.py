from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine

from app import ai_queue
from app.models import SessionTuteur, StatutTacheIA, TacheIA, TentativeQuiz, Utilisateur


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

def test_file_ia_notifie_redis_apres_planification(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ai_queue, "engine", engine)

    notifications = []
    monkeypatch.setattr(
        ai_queue,
        "notifier_tache",
        lambda tache_id: notifications.append(tache_id) or True,
    )

    with Session(engine) as session:
        utilisateur = Utilisateur(
            nom="TestRedis",
            telephone="690000002",
            mot_de_passe_hash="hash",
        )
        session.add(utilisateur)
        session.commit()
        session.refresh(utilisateur)

        tentative = TentativeQuiz(
            utilisateur_id=utilisateur.id,
            matiere="Informatique",
            niveau="L1",
            difficulte="Facile",
            nb_questions=1,
            questions_json="[]",
        )
        session.add(tentative)
        session.commit()
        session.refresh(tentative)

    tache_id = ai_queue.planifier_verification_quiz(tentative.id)

    assert tache_id is not None
    assert notifications == [tache_id]


def test_file_ia_prend_une_tache_par_id_redis(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ai_queue, "engine", engine)

    with Session(engine) as session:
        utilisateur = Utilisateur(
            nom="TestRedisId",
            telephone="690000003",
            mot_de_passe_hash="hash",
        )
        session.add(utilisateur)
        session.commit()
        session.refresh(utilisateur)

        tentative = TentativeQuiz(
            utilisateur_id=utilisateur.id,
            matiere="Chimie",
            niveau="L1",
            difficulte="Moyen",
            nb_questions=1,
            questions_json="[]",
        )
        session.add(tentative)
        session.commit()
        session.refresh(tentative)

    tache_id = ai_queue.planifier_verification_quiz(tentative.id)
    tache = ai_queue.prendre_tache(tache_id)

    assert tache is not None
    assert tache.id == tache_id
    assert tache.statut == StatutTacheIA.EN_COURS




def test_file_ia_planification_tuteur_idempotente(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ai_queue, "engine", engine)

    with Session(engine) as session:
        utilisateur = Utilisateur(
            nom="TestTuteur",
            telephone="690000005",
            mot_de_passe_hash="hash",
        )
        session.add(utilisateur)
        session.commit()
        session.refresh(utilisateur)

        session_tuteur = SessionTuteur(
            utilisateur_id=utilisateur.id,
            notion="Déterminant d'ordre 2",
            question="Explique-moi le déterminant.",
            explication="Réponse.",
            exemple="Exemple.",
            exercice="Exercice.",
            correction="Correction.",
            statut_verification_ia="en_attente",
        )
        session.add(session_tuteur)
        session.commit()
        session.refresh(session_tuteur)

        first = ai_queue.planifier_verification_tuteur(session_tuteur.id)
        second = ai_queue.planifier_verification_tuteur(session_tuteur.id)

        assert first == second

        tache = session.get(TacheIA, first)
        assert tache is not None
        assert tache.type_tache == ai_queue.TYPE_VERIFICATION_TUTEUR
        assert tache.session_tuteur_id == session_tuteur.id
        assert tache.tentative_quiz_id is None


def test_file_ia_reprend_une_tache_orpheline(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ai_queue, "engine", engine)

    with Session(engine) as session:
        utilisateur = Utilisateur(
            nom="TestOrphelin",
            telephone="690000006",
            mot_de_passe_hash="hash",
        )
        session.add(utilisateur)
        session.commit()
        session.refresh(utilisateur)

        session_tuteur = SessionTuteur(
            utilisateur_id=utilisateur.id,
            notion="Algèbre",
            question="Question.",
            explication="Réponse.",
            exemple="Exemple.",
            exercice="Exercice.",
            correction="Correction.",
            statut_verification_ia="en_cours",
        )
        session.add(session_tuteur)
        session.commit()
        session.refresh(session_tuteur)

        tache = TacheIA(
            type_tache=ai_queue.TYPE_VERIFICATION_TUTEUR,
            session_tuteur_id=session_tuteur.id,
            tentative_quiz_id=None,
            statut=StatutTacheIA.EN_COURS,
            strategie_verification="legere",
            prise_en_charge_le=datetime.utcnow(),
        )
        session.add(tache)
        session.commit()
        session.refresh(tache)
        tache_id = tache.id

    notifications = []
    monkeypatch.setattr(
        ai_queue,
        "notifier_tache",
        lambda task_id: notifications.append(task_id) or True,
    )

    assert ai_queue.reparer_taches_en_cours_orphelines(
        max_taches=5,
        age_secondes=1,
    ) == 1

    with Session(engine) as session:
        tache = session.get(TacheIA, tache_id)
        assert tache is not None
        assert tache.statut == StatutTacheIA.EN_ATTENTE
        assert tache.prise_en_charge_le is None
        assert tache.disponible_le is not None

    assert notifications == [tache_id]
