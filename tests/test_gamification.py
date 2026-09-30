from datetime import datetime, timedelta

from sqlmodel import Session, SQLModel, create_engine, select

from app import gamification
from app.models import ActionGamification, Utilisateur


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def _utilisateur(session):
    utilisateur = Utilisateur(
        nom="Etudiant Test",
        telephone="690000999",
        mot_de_passe_hash="hash",
    )
    session.add(utilisateur)
    session.commit()
    session.refresh(utilisateur)
    return utilisateur


def test_enregistrer_action_est_idempotent():
    _, session = _session()
    utilisateur = _utilisateur(session)

    premiere = gamification.enregistrer_action(
        session,
        utilisateur.id,
        "quiz",
        source_type="tentative_quiz",
        source_key="42",
    )
    session.commit()

    deuxieme = gamification.enregistrer_action(
        session,
        utilisateur.id,
        "quiz",
        source_type="tentative_quiz",
        source_key="42",
    )
    session.commit()

    actions = session.exec(select(ActionGamification)).all()
    assert premiere.id == deuxieme.id
    assert len(actions) == 1
    assert actions[0].points == 25


def test_resume_calcule_xp_missions_et_badges():
    _, session = _session()
    utilisateur = _utilisateur(session)

    for action, source_type, source_key in [
        ("tuteur", "session_tuteur", "1"),
        ("quiz", "tentative_quiz", "2"),
        ("cercle", "message_cercle", "3"),
        ("document", "document", "4"),
    ]:
        gamification.enregistrer_action(
            session,
            utilisateur.id,
            action,
            source_type=source_type,
            source_key=source_key,
        )
    session.commit()

    resume = gamification.resume(session, utilisateur)

    assert resume["total_xp"] == 125  # 100 XP des 4 missions + 25 XP de bonus journalier
    assert resume["bonus_mission"] == 25
    assert resume["mission_completee"] is True
    assert resume["niveau"] == 1
    assert resume["missions"]
    assert all(mission["terminee"] for mission in resume["missions"])
    assert any(badge["id"] == "premier_pas" and badge["obtenu"] for badge in resume["badges"])


def test_classement_place_l_utilisateur():
    _, session = _session()
    utilisateur = _utilisateur(session)
    autre = Utilisateur(
        nom="Autre Etudiant",
        telephone="690000998",
        mot_de_passe_hash="hash",
    )
    session.add(autre)
    session.commit()
    session.refresh(autre)

    gamification.enregistrer_action(
        session,
        autre.id,
        "quiz",
        source_type="tentative_quiz",
        source_key="10",
    )
    gamification.enregistrer_action(
        session,
        utilisateur.id,
        "tuteur",
        source_type="session_tuteur",
        source_key="20",
    )
    session.commit()

    classement = gamification.classement(session, utilisateur)

    assert classement["rang"] == 2
    assert classement["top"][0]["utilisateur_id"] == autre.id
