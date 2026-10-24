from datetime import datetime, timedelta
from sqlmodel import Session, SQLModel, create_engine, select

from app import learning_recap
from app.models import (
    ActionGamification,
    ConsultationDocument,
    Document,
    JeuCerebralSession,
    RoleUtilisateur,
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


def _quiz(user_id, when, score=4):
    return TentativeQuiz(
        utilisateur_id=user_id,
        matiere="Mathématiques",
        niveau="L1",
        difficulte="Facile",
        nb_questions=5,
        questions_json="[]",
        reponses_json="[0,1,2,3,4]",
        score=score,
        date_creation=when - timedelta(minutes=10),
        date_soumission=when,
    )


def test_normaliser_date_depuis_borne_les_dates_et_accepte_epoch_millisecondes():
    now = datetime(2026, 10, 24, 12, 0, 0)
    valeur = int((now - timedelta(hours=4)).timestamp() * 1000)

    assert learning_recap.normaliser_date_depuis(valeur, now) == now - timedelta(hours=4)
    assert learning_recap.normaliser_date_depuis((now + timedelta(days=3)).isoformat(), now) == now
    assert learning_recap.normaliser_date_depuis("date-invalide", now) == now - timedelta(days=1)
    assert learning_recap.normaliser_date_depuis(
        (now - timedelta(days=90)).isoformat(), now
    ) == now - timedelta(days=learning_recap.MAX_PERIODE_JOURS)


def test_bilan_reprise_agrège_les_sources_reelles_et_isole_les_comptes(monkeypatch):
    _engine, session = _db()
    now = datetime(2026, 10, 24, 12, 0, 0)
    depuis = now - timedelta(days=1)
    user = _user(session, "0341000001")
    other = _user(session, "0341000002")

    doc = Document(
        reference="MG-TEST-REPRISE-001",
        titre="Cours de fractions",
        matiere="Mathématiques",
        type_document=TypeDocument.COURS,
        annee=2025,
        filiere_id=1,
        portee_academique="universitaire",
        uploader_id=user.id,
        chemin_fichier="documents/test-cours.pdf",
        statut=StatutDocument.APPROUVE,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    session.add_all([
        _quiz(user.id, now - timedelta(hours=3), score=4),
        _quiz(user.id, now - timedelta(days=2), score=2),
        _quiz(other.id, now - timedelta(hours=1), score=5),
        ConsultationDocument(
            utilisateur_id=user.id,
            document_id=doc.id,
            date_consultation=now - timedelta(hours=2),
        ),
        SessionTuteur(
            utilisateur_id=user.id,
            notion="Fractions",
            question="Explique-moi les fractions équivalentes.",
            explication="Deux fractions équivalentes représentent la même valeur.",
            exemple="1/2 = 2/4",
            exercice="Écris une fraction équivalente à 1/3.",
            correction="2/6 est équivalente à 1/3.",
            date_creation=now - timedelta(hours=1, minutes=30),
        ),
        JeuCerebralSession(
            utilisateur_id=user.id,
            theme_id="logique_deduction",
            questions_json="[]",
            score=80,
            bonnes_reponses=4,
            nb_questions=5,
            date_creation=now - timedelta(hours=1, minutes=10),
            date_fin=now - timedelta(hours=1),
        ),
        ActionGamification(
            utilisateur_id=user.id,
            action="cercle_rejoint",
            source_type="cercle",
            source_key="42",
            points=10,
            date_creation=now - timedelta(minutes=30),
        ),
    ])
    session.commit()

    monkeypatch.setattr(
        learning_recap.subscription,
        "acces_ia_valide",
        lambda _abonnement: True,
    )
    bilan = learning_recap.construire_bilan(
        session,
        user,
        depuis=depuis.isoformat(),
        maintenant=now,
    )

    assert bilan["stats"] == {"quiz": 1, "documents": 1, "tuteur": 1, "jeux": 1}
    assert bilan["has_activity"] is True
    assert bilan["has_learning_data"] is False
    assert bilan["acces_ia"] is True
    assert bilan["mission"]["type"] == "nouvelle"
    assert any(item["type"] == "quiz" and item["score"] == 4 for item in bilan["activites"])
    assert any(item["type"] == "document" and item["titre"] == "Cours de fractions" for item in bilan["activites"])
    assert any(item["type"] == "tuteur" and item["notion"] == "Fractions" for item in bilan["activites"])
    assert any(item["type"] == "jeu" and item["score"] == 80 for item in bilan["activites"])
    assert any(
        item["type"] == "collaboration" and item["action"] == "cercle_rejoint"
        for item in bilan["activites"]
    )
    assert all("Apprenant test" not in str(item) for item in bilan["activites"])
    assert len(session.exec(select(TentativeQuiz).where(TentativeQuiz.utilisateur_id == other.id)).all()) == 1


def test_bilan_reprise_sans_donnees_est_honnete_et_ne_propose_pas_une_fausse_maitrise():
    _engine, session = _db()
    user = _user(session, "0341000003")

    bilan = learning_recap.construire_bilan(
        session,
        user,
        maintenant=datetime(2026, 10, 24, 12, 0, 0),
    )

    assert bilan["has_activity"] is False
    assert bilan["has_learning_data"] is False
    assert bilan["stats"] == {"quiz": 0, "documents": 0, "tuteur": 0, "jeux": 0}
    assert bilan["mission"]["type"] == "nouvelle"
    assert any(item["titre"] == "Accès aux outils IA" for item in bilan["methodes"])
    assert not any(item["titre"] == "Tuteur IA" for item in bilan["methodes"])
