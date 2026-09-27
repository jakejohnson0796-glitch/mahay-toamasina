"""
Tests de l'audit et de la réorganisation canonique des Cercles.
"""
import unittest

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import (
    CercleEtude,
    DemandeAdhesionCercle,
    Document,
    Faculte,
    Filiere,
    MembreCercle,
    Mention,
    MessageCercle,
    ProgrammeUniversitaire,
    RoleMembreCercle,
    RoleUtilisateur,
    StatutCercle,
    StatutDemandeAdhesion,
    StatutDocument,
    TypeDocument,
    Universite,
    Utilisateur,
)
from app.cercles_referentiel import assurer_cercles_referentiel
from scripts.dedupliquer_cercles_nationaux import deduplicquer


def nouvel_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def activer_fk(connexion, _record):
        connexion.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine


class TestReorganisationCercles(unittest.TestCase):
    def setUp(self):
        self.engine = nouvel_engine()
        with Session(self.engine) as session:
            admin = Utilisateur(
                nom="Admin",
                telephone="0340000001",
                mot_de_passe_hash="x",
                role=RoleUtilisateur.ADMIN,
            )
            alice = Utilisateur(
                nom="Alice",
                telephone="0340000002",
                mot_de_passe_hash="x",
                role=RoleUtilisateur.ETUDIANT,
            )
            bob = Utilisateur(
                nom="Bob",
                telephone="0340000003",
                mot_de_passe_hash="x",
                role=RoleUtilisateur.ETUDIANT,
            )
            charlie = Utilisateur(
                nom="Charlie",
                telephone="0340000004",
                mot_de_passe_hash="x",
                role=RoleUtilisateur.ETUDIANT,
            )
            session.add_all([admin, alice, bob, charlie])
            session.commit()
            session.refresh(admin)
            session.refresh(alice)
            session.refresh(bob)
            session.refresh(charlie)

            u1 = Universite(nom="Université A", ville="Toamasina", code="UA")
            u2 = Universite(nom="Université B", ville="Mahajanga", code="UB")
            session.add_all([u1, u2])
            session.commit()
            session.refresh(u1)
            session.refresh(u2)

            f1 = Faculte(nom="Faculté A", universite_id=u1.id)
            f2 = Faculte(nom="Faculté B", universite_id=u2.id)
            session.add_all([f1, f2])
            session.commit()
            session.refresh(f1)
            session.refresh(f2)

            mention = Mention(nom="Sciences de gestion")
            session.add(mention)
            session.commit()
            session.refresh(mention)

            p1 = Filiere(
                nom="Finance & Comptabilité",
                faculte_id=f1.id,
                mention_id=mention.id,
                niveau="M1",
            )
            p2 = Filiere(
                nom="Finance et Comptabilité",
                faculte_id=f2.id,
                mention_id=mention.id,
                niveau="M1",
            )
            session.add_all([p1, p2])
            session.commit()
            session.refresh(p1)
            session.refresh(p2)

            session.add_all([
                ProgrammeUniversitaire(universite_id=u1.id, filiere_id=p1.id, est_active=True),
                ProgrammeUniversitaire(universite_id=u2.id, filiere_id=p2.id, est_active=True),
            ])
            alice.universite_id = u1.id
            alice.mention_id = mention.id
            alice.filiere_id = p1.id
            alice.niveau = "M1"
            bob.universite_id = u2.id
            bob.mention_id = mention.id
            bob.filiere_id = p2.id
            bob.niveau = "M1"
            session.add_all([alice, bob])
            session.commit()

            self.admin_id = admin.id
            self.alice_id = alice.id
            self.bob_id = bob.id
            self.mention_id = mention.id
            self.p1_id = p1.id
            self.p2_id = p2.id

    def test_fusionne_les_doublons_nationaux_entre_filiere_ids(self):
        with Session(self.engine) as session:
            c1 = CercleEtude(
                nom="Finance M1 A",
                mention_id=self.mention_id,
                filiere_id=self.p1_id,
                niveau="M1",
                createur_id=self.admin_id,
                statut=StatutCercle.ACTIF,
            )
            c2 = CercleEtude(
                nom="Finance M1 B",
                mention_id=self.mention_id,
                filiere_id=self.p2_id,
                niveau="M1",
                createur_id=self.admin_id,
                statut=StatutCercle.ACTIF,
            )
            session.add_all([c1, c2])
            session.commit()
            session.refresh(c1)
            session.refresh(c2)

            session.add_all([
                MembreCercle(cercle_id=c1.id, utilisateur_id=self.alice_id, role=RoleMembreCercle.MEMBRE),
                MembreCercle(cercle_id=c2.id, utilisateur_id=self.bob_id, role=RoleMembreCercle.MEMBRE),
                MessageCercle(
                    cercle_id=c2.id,
                    auteur_id=self.bob_id,
                    contenu="Message du cercle doublon",
                ),
                Document(
                    reference="REORG-001",
                    titre="Cours Finance",
                    matiere="Finance",
                    type_document=TypeDocument.COURS,
                    annee=2026,
                    filiere_id=self.p2_id,
                    uploader_id=self.bob_id,
                    chemin_fichier="reorg-001.pdf",
                    statut=StatutDocument.APPROUVE,
                    cercle_id=c2.id,
                ),
                DemandeAdhesionCercle(
                    cercle_id=c2.id,
                    utilisateur_id=self.admin_id,
                    raison="Test",
                    statut=StatutDemandeAdhesion.EN_ATTENTE,
                ),
            ])
            session.commit()

            rapport = deduplicquer(session)

            actifs = session.exec(
                select(CercleEtude).where(CercleEtude.statut == StatutCercle.ACTIF)
            ).all()
            archives = session.exec(
                select(CercleEtude).where(CercleEtude.statut == StatutCercle.ARCHIVE)
            ).all()

            self.assertEqual(len(actifs), 1)
            self.assertEqual(len(archives), 1)
            self.assertEqual(len(rapport.groupes_fusionnes), 1)
            survivant = actifs[0]
            self.assertEqual(survivant.mention_id, self.mention_id)
            self.assertEqual(survivant.niveau, "M1")
            self.assertEqual(survivant.filiere_id, min(self.p1_id, self.p2_id))

            membres = session.exec(
                select(MembreCercle).where(MembreCercle.cercle_id == survivant.id)
            ).all()
            self.assertEqual(
                {m.utilisateur_id for m in membres},
                {self.alice_id, self.bob_id},
            )
            self.assertEqual(
                session.exec(select(MessageCercle).where(MessageCercle.cercle_id == survivant.id)).one().contenu,
                "Message du cercle doublon",
            )
            self.assertIsNotNone(
                session.exec(select(Document).where(Document.reference == "REORG-001")).one().cercle_id
            )
            self.assertEqual(
                session.exec(
                    select(DemandeAdhesionCercle).where(
                        DemandeAdhesionCercle.utilisateur_id == self.admin_id,
                    )
                ).one().cercle_id,
                survivant.id,
            )

            second = deduplicquer(session)
            self.assertEqual(second.groupes_fusionnes, [])
            self.assertEqual(
                len(session.exec(select(CercleEtude).where(CercleEtude.statut == StatutCercle.ACTIF)).all()),
                1,
            )

    def test_normalise_un_pseudo_tronc_commun(self):
        with Session(self.engine) as session:
            pseudo = Filiere(
                nom="Tronc commun",
                faculte_id=session.exec(select(Faculte)).first().id,
                mention_id=self.mention_id,
                niveau="L1",
            )
            session.add(pseudo)
            session.commit()
            session.refresh(pseudo)
            session.add(
                ProgrammeUniversitaire(
                    universite_id=session.exec(select(Universite)).first().id,
                    filiere_id=pseudo.id,
                    est_active=True,
                )
            )
            c_pseudo = CercleEtude(
                nom="Tronc commun — L1",
                mention_id=self.mention_id,
                filiere_id=pseudo.id,
                niveau="L1",
                createur_id=self.admin_id,
                statut=StatutCercle.ACTIF,
            )
            c_tronc = CercleEtude(
                nom="Tronc commun Gestion L1",
                mention_id=self.mention_id,
                filiere_id=None,
                niveau="L1",
                createur_id=self.admin_id,
                statut=StatutCercle.ACTIF,
            )
            session.add_all([c_pseudo, c_tronc])
            session.commit()

            rapport = deduplicquer(session)

            actifs = session.exec(
                select(CercleEtude).where(CercleEtude.statut == StatutCercle.ACTIF)
            ).all()
            archives = session.exec(
                select(CercleEtude).where(CercleEtude.statut == StatutCercle.ARCHIVE)
            ).all()

            self.assertEqual(len(actifs), 1)
            self.assertIsNone(actifs[0].filiere_id)
            self.assertEqual(len(archives), 1)
            self.assertEqual(rapport.pseudo_tronc_normalises, 1)

    def test_ne_cree_plus_les_huit_niveaux_sans_niveau_verifie(self):
        with Session(self.engine) as session:
            filiere = Filiere(
                nom="Parcours sans niveau",
                faculte_id=session.exec(select(Faculte)).first().id,
                mention_id=self.mention_id,
                niveau=None,
            )
            session.add(filiere)
            session.commit()
            session.refresh(filiere)
            session.add(
                ProgrammeUniversitaire(
                    universite_id=session.exec(select(Universite)).first().id,
                    filiere_id=filiere.id,
                    est_active=True,
                )
            )
            session.commit()

            self.assertEqual(assurer_cercles_referentiel(session), 0)
            self.assertEqual(
                session.exec(
                    select(CercleEtude).where(CercleEtude.filiere_id == filiere.id)
                ).all(),
                [],
            )

    def test_archive_un_ancien_cercle_sans_niveau_verifie(self):
        with Session(self.engine) as session:
            filiere = Filiere(
                nom="Ancien parcours sans niveau",
                faculte_id=session.exec(select(Faculte)).first().id,
                mention_id=self.mention_id,
                niveau=None,
            )
            session.add(filiere)
            session.commit()
            session.refresh(filiere)
            session.add(
                ProgrammeUniversitaire(
                    universite_id=session.exec(select(Universite)).first().id,
                    filiere_id=filiere.id,
                    est_active=True,
                )
            )
            cercle = CercleEtude(
                nom="Ancien parcours L1",
                mention_id=self.mention_id,
                filiere_id=filiere.id,
                niveau="L1",
                createur_id=self.admin_id,
                statut=StatutCercle.ACTIF,
            )
            session.add(cercle)
            session.commit()

            rapport = deduplicquer(session)

            self.assertEqual(
                session.get(CercleEtude, cercle.id).statut,
                StatutCercle.ARCHIVE,
            )
            self.assertEqual(len(rapport.cercles_suspects), 0)

    def test_archive_un_cercle_incomplet_sans_contenu_mais_conserve_un_suspect(self):
        with Session(self.engine) as session:
            suspect_vide = CercleEtude(
                nom="Cercle suspect vide",
                mention_id=self.mention_id,
                niveau=None,
                createur_id=self.admin_id,
                statut=StatutCercle.ACTIF,
            )
            suspect_habite = CercleEtude(
                nom="Cercle suspect avec membre",
                mention_id=self.mention_id,
                niveau=None,
                createur_id=self.admin_id,
                statut=StatutCercle.ACTIF,
            )
            session.add_all([suspect_vide, suspect_habite])
            session.commit()
            session.refresh(suspect_habite)
            session.add(
                MembreCercle(
                    cercle_id=suspect_habite.id,
                    utilisateur_id=self.bob_id,
                    role=RoleMembreCercle.MEMBRE,
                )
            )
            session.commit()

            rapport = deduplicquer(session)

            self.assertEqual(
                session.get(CercleEtude, suspect_vide.id).statut,
                StatutCercle.ARCHIVE,
            )
            self.assertEqual(
                session.get(CercleEtude, suspect_habite.id).statut,
                StatutCercle.ACTIF,
            )
            self.assertEqual(len(rapport.cercles_suspects), 1)
            self.assertEqual(rapport.cercles_suspects[0]["id"], suspect_habite.id)

    def test_le_provisionnement_ne_recree_plus_un_pseudo_tronc(self):
        with Session(self.engine) as session:
            pseudo = Filiere(
                nom="Tronc commun",
                faculte_id=session.exec(select(Faculte)).first().id,
                mention_id=self.mention_id,
                niveau="L1",
            )
            session.add(pseudo)
            session.commit()
            session.refresh(pseudo)
            session.add(
                ProgrammeUniversitaire(
                    universite_id=session.exec(select(Universite)).first().id,
                    filiere_id=pseudo.id,
                    est_active=True,
                )
            )
            session.commit()

            assurer_cercles_referentiel(session)
            cercles_pseudo = session.exec(
                select(CercleEtude).where(CercleEtude.filiere_id == pseudo.id)
            ).all()
            self.assertEqual(cercles_pseudo, [])


if __name__ == "__main__":
    unittest.main()
