from datetime import timedelta

from sqlmodel import Session, SQLModel, create_engine, select

from app import onboarding
from app.models import ActionGamification, Utilisateur


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def _user(session):
    utilisateur = Utilisateur(
        nom="Nouvel Etudiant",
        telephone="690001234",
        mot_de_passe_hash="hash",
    )
    session.add(utilisateur)
    session.commit()
    session.refresh(utilisateur)
    return utilisateur


def test_onboarding_demarre_et_affiche_trois_etapes():
    _, session = _session()
    utilisateur = _user(session)

    donnees = onboarding.donnees_onboarding(session, utilisateur)

    assert donnees["jour"] == 1
    assert donnees["etapes_terminees"] == 0
    assert donnees["onboarding_termine"] is False
    assert len(donnees["etapes"]) == 3


def test_onboarding_se_termine_apres_trois_actions():
    _, session = _session()
    utilisateur = _user(session)

    for action in ("tuteur", "quiz", "cercle_rejoint"):
        session.add(
            ActionGamification(
                utilisateur_id=utilisateur.id,
                action=action,
                source_type="test",
                source_key=action,
                points=10,
            )
        )
    session.commit()

    donnees = onboarding.donnees_onboarding(session, utilisateur)

    assert donnees["onboarding_termine"] is True
    session.refresh(utilisateur)
    assert utilisateur.onboarding_termine_le is not None


def test_onboarding_semaine_marque_les_actions_realisees():
    _, session = _session()
    utilisateur = _user(session)
    debut = onboarding.assurer_demarrage(session, utilisateur)

    session.add(
        ActionGamification(
            utilisateur_id=utilisateur.id,
            action="quiz",
            source_type="test",
            source_key="quiz-1",
            points=25,
            date_creation=debut + timedelta(days=1, minutes=1),
        )
    )
    session.commit()

    donnees = onboarding.donnees_onboarding(session, utilisateur)

    jour1 = next(item for item in donnees["plan_7_jours"] if item["jour"] == 1)
    jour2 = next(item for item in donnees["plan_7_jours"] if item["jour"] == 2)

    assert jour1["terminee"] is False
    assert jour2["terminee"] is True
