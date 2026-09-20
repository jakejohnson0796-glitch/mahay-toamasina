"""
Tests d'integrite des donnees des cercles.

Ces tests couvrent les invariants qui etaient jusque-la proteges surtout
par des verifications applicatives non atomiques :
- une seule appartenance par utilisateur/cercle ;
- une seule reaction active par utilisateur/message ;
- une seule demande de creation nationale en attente par identite ;
- une seule plainte ouverte par utilisateur/message ;
- suppression d'un cercle sans laisser de FK orphelines.
"""
import unittest
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import (
    AbonnementEtudiant,
    CercleEtude,
    DemandeAdhesionCercle,
    DemandeCreationCercle,
    MembreCercle,
    Document,
    Faculte,
    Filiere,
    Mention,
    MessageCercle,
    MessageMention,
    MessageReaction,
    Notification,
    RoleMembreCercle,
    RoleUtilisateur,
    SignalementMessage,
    StatutCercle,
    StatutDemandeCreationCercle,
    ThemeDuJour,
    TypeNotification,
    TypeReaction,
    TypeDocument,
    StatutDocument,
    Universite,
    Utilisateur,
)
from app.routers.cercles_router import _supprimer_cercle_et_contenu


class TestIntegriteCercles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(cls.engine)

    def setUp(self):
        with Session(self.engine) as session:
            # Ordre enfants -> parents pour respecter les FK.
            for table in (
                Notification,
                MessageMention,
                MessageReaction,
                SignalementMessage,
                MessageCercle,
                DemandeAdhesionCercle,
                DemandeCreationCercle,
                Document,
                ThemeDuJour,
                AbonnementEtudiant,
                CercleEtude,
                Utilisateur,
                Filiere,
                Mention,
                Faculte,
                Universite,
            ):
                for ligne in session.exec(select(table)).all():
                    session.delete(ligne)
            session.commit()

            universite = Universite(nom="Universite Test Integrite", ville="Toamasina", code="UTESTINT")
            session.add(universite)
            session.commit()
            session.refresh(universite)

            faculte = Faculte(nom="Faculte Test Integrite", universite_id=universite.id)
            session.add(faculte)
            session.commit()
            session.refresh(faculte)

            mention = Mention(nom="Mention Test Integrite")
            session.add(mention)
            session.commit()
            session.refresh(mention)

            filiere = Filiere(
                nom="Parcours Test Integrite",
                faculte_id=faculte.id,
                mention_id=mention.id,
            )
            session.add(filiere)
            session.commit()
            session.refresh(filiere)

            alice = Utilisateur(
                nom="Alice",
                telephone="0380000001",
                mot_de_passe_hash="x",
                role=RoleUtilisateur.ETUDIANT,
                mention_id=mention.id,
                filiere_id=filiere.id,
                universite_id=universite.id,
                niveau="L3",
            )
            bob = Utilisateur(
                nom="Bob",
                telephone="0380000002",
                mot_de_passe_hash="x",
                role=RoleUtilisateur.ETUDIANT,
                mention_id=mention.id,
                filiere_id=filiere.id,
                universite_id=universite.id,
                niveau="L3",
            )
            session.add(alice)
            session.add(bob)
            session.commit()
            session.refresh(alice)
            session.refresh(bob)

            self.alice_id = alice.id
            self.bob_id = bob.id
            self.mention_id = mention.id
            self.filiere_id = filiere.id
            self.universite_id = universite.id

            cercle = CercleEtude(
                nom="Cercle Test Integrite",
                mention_id=mention.id,
                filiere_id=filiere.id,
                niveau="L3",
                createur_id=alice.id,
                statut=StatutCercle.ACTIF,
            )
            session.add(cercle)
            session.commit()
            session.refresh(cercle)
            self.cercle_id = cercle.id

            session.add(MembreCercle(
                cercle_id=cercle.id,
                utilisateur_id=alice.id,
                role=RoleMembreCercle.CREATEUR,
            ))
            session.commit()

            message = MessageCercle(
                cercle_id=cercle.id,
                auteur_id=alice.id,
                contenu="Message de test",
            )
            session.add(message)
            session.commit()
            session.refresh(message)
            self.message_id = message.id

    def test_une_seule_appartenance_par_utilisateur(self):
        with self.assertRaises(IntegrityError):
            with Session(self.engine) as session:
                session.add(MembreCercle(
                    cercle_id=self.cercle_id,
                    utilisateur_id=self.alice_id,
                    role=RoleMembreCercle.MEMBRE,
                ))
                session.commit()

    def test_une_seule_reaction_par_utilisateur_et_message(self):
        with Session(self.engine) as session:
            session.add(MessageReaction(
                message_id=self.message_id,
                utilisateur_id=self.bob_id,
                type_reaction=TypeReaction.POUCE,
            ))
            session.commit()

        with self.assertRaises(IntegrityError):
            with Session(self.engine) as session:
                session.add(MessageReaction(
                    message_id=self.message_id,
                    utilisateur_id=self.bob_id,
                    type_reaction=TypeReaction.COEUR,
                ))
                session.commit()

    def test_une_seule_demande_creation_nationale_en_attente(self):
        with Session(self.engine) as session:
            session.add(DemandeCreationCercle(
                utilisateur_id=self.alice_id,
                mention_id=self.mention_id,
                filiere_id=self.filiere_id,
                niveau="L3",
                nom="Cercle demande 1",
                raison="Reviser ensemble",
                statut=StatutDemandeCreationCercle.EN_ATTENTE,
            ))
            session.commit()

        with self.assertRaises(IntegrityError):
            with Session(self.engine) as session:
                session.add(DemandeCreationCercle(
                    utilisateur_id=self.bob_id,
                    mention_id=self.mention_id,
                    filiere_id=self.filiere_id,
                    niveau="L3",
                    nom="Cercle demande 2",
                    raison="Autre demande concurrente",
                    statut=StatutDemandeCreationCercle.EN_ATTENTE,
                ))
                session.commit()

    def test_une_seule_demande_creation_tronc_commun_en_attente(self):
        with Session(self.engine) as session:
            session.add(DemandeCreationCercle(
                utilisateur_id=self.alice_id,
                mention_id=self.mention_id,
                filiere_id=None,
                niveau="L1",
                nom="Tronc 1",
                raison="Discussion L1",
                statut=StatutDemandeCreationCercle.EN_ATTENTE,
            ))
            session.commit()

        with self.assertRaises(IntegrityError):
            with Session(self.engine) as session:
                session.add(DemandeCreationCercle(
                    utilisateur_id=self.bob_id,
                    mention_id=self.mention_id,
                    filiere_id=None,
                    niveau="L1",
                    nom="Tronc 2",
                    raison="Deuxieme demande",
                    statut=StatutDemandeCreationCercle.EN_ATTENTE,
                ))
                session.commit()

    def test_une_seule_plainte_non_traitee_par_utilisateur_message(self):
        with Session(self.engine) as session:
            session.add(SignalementMessage(
                message_id=self.message_id,
                signale_par_id=self.bob_id,
                motif="Spam",
                traite=False,
            ))
            session.commit()

        with self.assertRaises(IntegrityError):
            with Session(self.engine) as session:
                session.add(SignalementMessage(
                    message_id=self.message_id,
                    signale_par_id=self.bob_id,
                    motif="Autre",
                    traite=False,
                ))
                session.commit()

    def test_suppression_cercle_detache_les_references_externes_et_nettoie_le_chat(self):
        with Session(self.engine) as session:
            cercle = session.get(CercleEtude, self.cercle_id)
            message = session.get(MessageCercle, self.message_id)

            document = Document(
                reference="TEST-INTEGRITE-001",
                titre="Document test",
                matiere="Test",
                type_document=TypeDocument.FICHE,
                annee=2026,
                filiere_id=self.filiere_id,
                uploader_id=self.alice_id,
                chemin_fichier="test.pdf",
                statut=StatutDocument.APPROUVE,
                cercle_id=cercle.id,
            )
            theme = ThemeDuJour(
                date_jour=date(2026, 9, 20),
                theme="Theme test",
                amorce="Amorce test",
                cercle_id=cercle.id,
            )
            demande_creation = DemandeCreationCercle(
                utilisateur_id=self.alice_id,
                mention_id=self.mention_id,
                filiere_id=self.filiere_id,
                niveau="L2",
                nom="Demande historique",
                raison="Historique",
                statut=StatutDemandeCreationCercle.APPROUVEE,
                cercle_cree_id=cercle.id,
            )
            notification = Notification(
                destinataire_id=self.bob_id,
                type_notification=TypeNotification.MENTION,
                contenu="Notification test",
                cercle_id=cercle.id,
                message_id=message.id,
            )
            reaction = MessageReaction(
                message_id=message.id,
                utilisateur_id=self.bob_id,
                type_reaction=TypeReaction.POUCE,
            )
            mention = MessageMention(
                message_id=message.id,
                utilisateur_mentionne_id=self.bob_id,
            )
            session.add_all([
                document, theme, demande_creation, notification,
                reaction, mention,
            ])
            session.commit()
            session.refresh(document)
            session.refresh(theme)
            session.refresh(demande_creation)

            _supprimer_cercle_et_contenu(session, cercle.id)
            session.commit()

            self.document_id = document.id
            self.theme_id = theme.id
            self.demande_creation_id = demande_creation.id

        with Session(self.engine) as session:
            self.assertIsNone(session.get(CercleEtude, self.cercle_id))
            self.assertIsNone(session.get(MessageCercle, self.message_id))
            self.assertIsNone(session.get(MessageReaction, reaction.id))
            self.assertIsNone(session.get(MessageMention, mention.id))
            self.assertIsNone(session.get(Notification, notification.id))

            document = session.get(Document, self.document_id)
            self.assertIsNotNone(document)
            self.assertIsNone(document.cercle_id)

            theme = session.get(ThemeDuJour, self.theme_id)
            self.assertIsNotNone(theme)
            self.assertIsNone(theme.cercle_id)

            demande = session.get(DemandeCreationCercle, self.demande_creation_id)
            self.assertIsNotNone(demande)
            self.assertIsNone(demande.cercle_cree_id)


if __name__ == "__main__":
    unittest.main()
