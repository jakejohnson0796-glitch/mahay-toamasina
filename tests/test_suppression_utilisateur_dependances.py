import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlmodel import SQLModel, Session, create_engine, select

from app.models import (
    ActionGamification,
    CodeReinitialisationMotDePasse,
    CodeSecours2FA,
    DemandeChangementFiliere,
    DemandeCreationCercle,
    DemandeAdhesionCercle,
    FAQ,
    Feedback,
    MessageCercle,
    MessageMention,
    MessageReaction,
    Notification,
    ProgressionNotion,
    ReponseFeedback,
    RoleUtilisateur,
    SignalementMessage,
    StatutDemandeAdhesion,
    StatutDemandeChangementFiliere,
    StatutDemandeCreationCercle,
    StatutFeedback,
    TacheIA,
    TentativeQuiz,
    TypeNotification,
    Utilisateur,
)
from app.routers import admin_router


def test_suppression_utilisateur_nettoie_les_dependances_directes(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        admin = Utilisateur(
            nom="Admin courant",
            telephone="0340007001",
            mot_de_passe_hash="hash-admin",
            role=RoleUtilisateur.ADMIN,
        )
        cible = Utilisateur(
            nom="Admin a supprimer",
            telephone="0340007002",
            mot_de_passe_hash="hash-cible",
            role=RoleUtilisateur.ADMIN,
        )
        session.add(admin)
        session.add(cible)
        session.commit()
        session.refresh(admin)
        session.refresh(cible)

        session.add(ProgressionNotion(
            utilisateur_id=cible.id,
            matiere="Maths",
            notion="Suites",
        ))
        session.add(ActionGamification(
            utilisateur_id=cible.id,
            action="quiz",
            source_type="test",
            source_key="1",
            points=10,
        ))
        session.add(CodeSecours2FA(
            utilisateur_id=cible.id,
            code_hash="hash-code",
        ))
        session.add(CodeReinitialisationMotDePasse(
            utilisateur_id=cible.id,
            code_hash="hash-reset",
            expire_le=datetime.utcnow() + timedelta(minutes=15),
        ))

        tentative = TentativeQuiz(
            utilisateur_id=cible.id,
            matiere="Maths",
            niveau="L1",
            difficulte="facile",
            nb_questions=1,
            questions_json="[]",
        )
        session.add(tentative)
        session.commit()
        session.refresh(tentative)
        tache = TacheIA(
            type_tache="verification_quiz",
            tentative_quiz_id=tentative.id,
        )
        session.add(tache)

        message_cible = MessageCercle(
            cercle_id=1,
            auteur_id=cible.id,
            contenu="secret a supprimer",
        )
        message_admin = MessageCercle(
            cercle_id=1,
            auteur_id=admin.id,
            contenu="message conserve",
        )
        session.add(message_cible)
        session.add(message_admin)
        session.commit()
        session.refresh(message_cible)
        session.refresh(message_admin)

        session.add(MessageReaction(
            message_id=message_cible.id,
            utilisateur_id=admin.id,
            type_reaction="pouce",
        ))
        session.add(MessageReaction(
            message_id=message_admin.id,
            utilisateur_id=cible.id,
            type_reaction="coeur",
        ))
        session.add(MessageMention(
            message_id=message_cible.id,
            utilisateur_mentionne_id=admin.id,
        ))
        session.add(MessageMention(
            message_id=message_admin.id,
            utilisateur_mentionne_id=cible.id,
        ))

        notif_recue = Notification(
            destinataire_id=cible.id,
            type_notification=TypeNotification.MENTION,
            contenu="notification privee",
            acteur_id=admin.id,
        )
        notif_acteur = Notification(
            destinataire_id=admin.id,
            type_notification=TypeNotification.MENTION,
            contenu="notification de l'ancien compte",
            acteur_id=cible.id,
        )
        session.add(notif_recue)
        session.add(notif_acteur)

        feedback_cible = Feedback(
            utilisateur_id=cible.id,
            note=5,
            commentaire="mon avis",
            statut=StatutFeedback.NOUVEAU,
        )
        feedback_admin = Feedback(
            utilisateur_id=admin.id,
            note=4,
            commentaire="avis a conserver",
            statut=StatutFeedback.REPONDU,
        )
        session.add(feedback_cible)
        session.add(feedback_admin)
        session.commit()
        session.refresh(feedback_admin)

        session.add(ReponseFeedback(
            feedback_id=feedback_admin.id,
            admin_id=cible.id,
            reponse="reponse historique",
        ))
        session.add(FAQ(
            question="Question",
            reponse="Reponse",
            cree_par_id=cible.id,
        ))
        session.add(DemandeCreationCercle(
            utilisateur_id=cible.id,
            nom="Demande cible",
            raison="raison",
            statut=StatutDemandeCreationCercle.EN_ATTENTE,
        ))
        demande_creation_traitee = DemandeCreationCercle(
            utilisateur_id=admin.id,
            nom="Demande traitee",
            raison="raison",
            statut=StatutDemandeCreationCercle.REJETEE,
            traite_par_id=cible.id,
        )
        session.add(demande_creation_traitee)
        session.add(DemandeChangementFiliere(
            utilisateur_id=cible.id,
            motif="changement",
            statut=StatutDemandeChangementFiliere.EN_ATTENTE,
        ))
        demande_filiere_traitee = DemandeChangementFiliere(
            utilisateur_id=admin.id,
            motif="historique",
            statut=StatutDemandeChangementFiliere.REJETEE,
            traite_par_id=cible.id,
        )
        session.add(demande_filiere_traitee)
        session.add(DemandeAdhesionCercle(
            cercle_id=1,
            utilisateur_id=cible.id,
            statut=StatutDemandeAdhesion.EN_ATTENTE,
        ))
        demande_adhesion_traitee = DemandeAdhesionCercle(
            cercle_id=1,
            utilisateur_id=admin.id,
            statut=StatutDemandeAdhesion.REJETEE,
            traite_par_id=cible.id,
        )
        session.add(demande_adhesion_traitee)
        session.add(SignalementMessage(
            message_id=message_cible.id,
            signale_par_id=admin.id,
            motif="test",
        ))
        session.commit()

        class FakeRequest:
            async def form(self):
                return {}

        monkeypatch.setattr(admin_router, "_admin_requis", lambda request, session: admin)

        reponse = asyncio.run(
            admin_router.supprimer_utilisateur(
                FakeRequest(),
                cible.id,
                session,
                None,
            )
        )
        assert reponse.status_code == 303

        session.expire_all()
        assert session.get(Utilisateur, cible.id) is None

        assert session.exec(select(ProgressionNotion).where(ProgressionNotion.utilisateur_id == cible.id)).all() == []
        assert session.exec(select(ActionGamification).where(ActionGamification.utilisateur_id == cible.id)).all() == []
        assert session.exec(select(CodeSecours2FA).where(CodeSecours2FA.utilisateur_id == cible.id)).all() == []
        assert session.exec(select(CodeReinitialisationMotDePasse).where(CodeReinitialisationMotDePasse.utilisateur_id == cible.id)).all() == []
        assert session.exec(select(TentativeQuiz).where(TentativeQuiz.utilisateur_id == cible.id)).all() == []
        assert session.exec(select(TacheIA).where(TacheIA.tentative_quiz_id == tentative.id)).all() == []

        message = session.get(MessageCercle, message_cible.id)
        assert message is not None
        assert message.supprime is True
        assert message.auteur_id == admin.id
        assert message.contenu == "Message supprimé"
        assert session.exec(select(MessageReaction).where(MessageReaction.utilisateur_id == cible.id)).all() == []
        assert session.exec(select(MessageMention).where(MessageMention.utilisateur_mentionne_id == cible.id)).all() == []

        assert session.exec(select(Notification).where(Notification.destinataire_id == cible.id)).all() == []
        notification = session.get(Notification, notif_acteur.id)
        assert notification is not None
        assert notification.acteur_id is None

        assert session.exec(select(Feedback).where(Feedback.utilisateur_id == cible.id)).all() == []
        reponse_feedback = session.exec(
            select(ReponseFeedback).where(ReponseFeedback.feedback_id == feedback_admin.id)
        ).one()
        assert reponse_feedback.admin_id == admin.id

        faq = session.exec(select(FAQ).where(FAQ.question == "Question")).one()
        assert faq.cree_par_id is None

        assert session.exec(select(DemandeCreationCercle).where(DemandeCreationCercle.utilisateur_id == cible.id)).all() == []
        assert session.exec(select(DemandeChangementFiliere).where(DemandeChangementFiliere.utilisateur_id == cible.id)).all() == []
        assert session.exec(select(DemandeAdhesionCercle).where(DemandeAdhesionCercle.utilisateur_id == cible.id)).all() == []

        creation_traitee = session.get(DemandeCreationCercle, demande_creation_traitee.id)
        filiere_traitee = session.get(DemandeChangementFiliere, demande_filiere_traitee.id)
        adhesion_traitee = session.get(DemandeAdhesionCercle, demande_adhesion_traitee.id)
        assert creation_traitee.traite_par_id is None
        assert filiere_traitee.traite_par_id is None
        assert adhesion_traitee.traite_par_id is None
