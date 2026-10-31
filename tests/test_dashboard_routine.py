from datetime import datetime, timedelta

from sqlmodel import Session, SQLModel, create_engine

from app.dashboard import routine_du_jour
from app.models import (
    ActionGamification,
    ConsultationDocument,
    Document,
    SessionTuteur,
    StatutDocument,
    TentativeQuiz,
    TypeDocument,
    Utilisateur,
)


def _db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def _user(session, telephone):
    user = Utilisateur(
        nom="Apprenant test",
        telephone=telephone,
        mot_de_passe_hash="hash",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _document(session, utilisateur_id, statut=StatutDocument.APPROUVE):
    document = Document(
        reference=f"MG-ROUTINE-{utilisateur_id:04d}",
        titre="Cours de démonstration",
        matiere="Mathématiques",
        type_document=TypeDocument.COURS,
        annee=2026,
        uploader_id=utilisateur_id,
        chemin_fichier="documents/cours-routine.pdf",
        statut=statut,
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


def _quiz(utilisateur_id, quand):
    return TentativeQuiz(
        utilisateur_id=utilisateur_id,
        matiere="Mathématiques",
        niveau="L1",
        difficulte="Facile",
        nb_questions=5,
        questions_json="[]",
        score=4,
        date_creation=quand - timedelta(minutes=5),
        date_soumission=quand,
    )


def test_routine_vide_ne_declare_aucune_activite():
    _engine, session = _db()
    user = _user(session, "0341999001")

    routine = routine_du_jour(
        session,
        user.id,
        maintenant=datetime(2026, 10, 31, 12, 0),
    )

    assert routine["terminees"] == 0
    assert routine["total"] == 3
    assert routine["pourcentage"] == 0
    assert routine["complete"] is False
    assert all(not etape["terminee"] for etape in routine["etapes"])


def test_routine_compte_les_trois_activites_reelles_du_compte():
    _engine, session = _db()
    user = _user(session, "0341999002")
    maintenant = datetime(2026, 10, 31, 12, 0)
    document = _document(session, user.id)

    session.add_all([
        _quiz(user.id, maintenant - timedelta(hours=2)),
        ConsultationDocument(
            utilisateur_id=user.id,
            document_id=document.id,
            date_consultation=maintenant - timedelta(hours=1),
        ),
        SessionTuteur(
            utilisateur_id=user.id,
            notion="Fractions",
            question="Explique-moi les fractions équivalentes.",
            explication="Deux fractions sont équivalentes lorsqu'elles représentent la même valeur.",
            exemple="1/2 = 2/4",
            exercice="Donne une fraction équivalente à 1/3.",
            correction="2/6 convient.",
            date_creation=maintenant - timedelta(minutes=30),
        ),
    ])
    session.commit()

    routine = routine_du_jour(session, user.id, maintenant=maintenant)

    assert routine["terminees"] == 3
    assert routine["pourcentage"] == 100
    assert routine["complete"] is True
    assert {etape["id"] for etape in routine["etapes"] if etape["terminee"]} == {
        "quiz", "document", "interaction"
    }


def test_routine_isole_le_compte_et_ignore_les_activites_des_jours_precedents():
    _engine, session = _db()
    user = _user(session, "0341999003")
    other = _user(session, "0341999004")
    maintenant = datetime(2026, 10, 31, 12, 0)
    hier = maintenant - timedelta(days=1)
    document = _document(session, other.id)

    session.add_all([
        _quiz(other.id, maintenant - timedelta(hours=1)),
        ConsultationDocument(
            utilisateur_id=other.id,
            document_id=document.id,
            date_consultation=maintenant - timedelta(minutes=30),
        ),
        ActionGamification(
            utilisateur_id=other.id,
            action="cercle",
            source_type="message_cercle",
            source_key="900",
            points=20,
            date_creation=maintenant - timedelta(minutes=20),
        ),
        _quiz(user.id, hier),
        ConsultationDocument(
            utilisateur_id=user.id,
            document_id=document.id,
            date_consultation=hier,
        ),
        ActionGamification(
            utilisateur_id=user.id,
            action="cercle_rejoint",
            source_type="cercle",
            source_key="42",
            points=10,
            date_creation=maintenant - timedelta(minutes=10),
        ),
    ])
    session.commit()

    routine = routine_du_jour(session, user.id, maintenant=maintenant)

    assert routine["terminees"] == 0
    assert all(not etape["terminee"] for etape in routine["etapes"])


def test_routine_ne_compte_pas_un_document_non_approuve():
    _engine, session = _db()
    user = _user(session, "0341999005")
    maintenant = datetime(2026, 10, 31, 12, 0)
    document = _document(session, user.id, statut=StatutDocument.REJETE)

    session.add(ConsultationDocument(
        utilisateur_id=user.id,
        document_id=document.id,
        date_consultation=maintenant - timedelta(minutes=10),
    ))
    session.commit()

    routine = routine_du_jour(session, user.id, maintenant=maintenant)

    assert routine["terminees"] == 0
    assert routine["etapes"][1]["terminee"] is False


def test_message_dans_un_cercle_compte_comme_interaction_reelle():
    _engine, session = _db()
    user = _user(session, "0341999006")
    maintenant = datetime(2026, 10, 31, 12, 0)

    session.add(ActionGamification(
        utilisateur_id=user.id,
        action="cercle",
        source_type="message_cercle",
        source_key="901",
        points=20,
        date_creation=maintenant - timedelta(minutes=5),
    ))
    session.commit()

    routine = routine_du_jour(session, user.id, maintenant=maintenant)

    assert routine["etapes"][2]["terminee"] is True
    assert routine["terminees"] == 1
