"""Tests du traitement des demandes d'adhésion par admin vs créateur."""
import unittest

from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine

from app.models import (
    CercleEtude,
    DemandeAdhesionCercle,
    Faculte,
    Filiere,
    MembreCercle,
    Mention,
    ProgrammeUniversitaire,
    RoleMembreCercle,
    RoleUtilisateur,
    StatutCercle,
    StatutDemandeAdhesion,
    Universite,
    Utilisateur,
)
from app.routers.cercles_router import _traiter_acceptation_demande


def nouvel_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def fk(connexion, _record):
        connexion.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine


class TestAcceptationDemandesAdhesion(unittest.TestCase):
    def _fixture(self):
        engine = nouvel_engine()
        with Session(engine) as s:
            admin = Utilisateur(
                nom="Admin",
                telephone="0340001001",
                mot_de_passe_hash="x",
                role=RoleUtilisateur.ADMIN,
            )
            createur = Utilisateur(
                nom="Createur",
                telephone="0340001002",
                mot_de_passe_hash="x",
                role=RoleUtilisateur.ETUDIANT,
            )
            demandeur = Utilisateur(
                nom="Demandeur",
                telephone="0340001003",
                mot_de_passe_hash="x",
                role=RoleUtilisateur.ETUDIANT,
            )
            s.add(admin); s.add(createur); s.add(demandeur)
            s.commit()
            s.refresh(admin); s.refresh(createur); s.refresh(demandeur)

            u = Universite(nom="Universite de Toamasina")
            s.add(u); s.commit(); s.refresh(u)
            f = Faculte(nom="DEGMIA", universite_id=u.id)
            m = Mention(nom="Gestion")
            s.add(f); s.add(m); s.commit(); s.refresh(f); s.refresh(m)
            filiere = Filiere(
                nom="Commerce International",
                faculte_id=f.id,
                mention_id=m.id,
                niveau="M1",
            )
            s.add(filiere); s.commit(); s.refresh(filiere)
            s.add(ProgrammeUniversitaire(
                universite_id=u.id,
                filiere_id=filiere.id,
                est_active=True,
            ))
            s.commit()

            cercle = CercleEtude(
                nom="Commerce International M1",
                createur_id=createur.id,
                mention_id=m.id,
                filiere_id=filiere.id,
                niveau="M1",
                statut=StatutCercle.ACTIF,
            )
            s.add(cercle); s.commit(); s.refresh(cercle)

            # Le profil change APRES la demande : l'étudiant est maintenant L2.
            demandeur.universite_id = u.id
            demandeur.faculte_id = f.id
            demandeur.mention_id = m.id
            demandeur.filiere_id = filiere.id
            demandeur.niveau = "L2"
            s.add(demandeur)
            s.commit()

            demande = DemandeAdhesionCercle(
                cercle_id=cercle.id,
                utilisateur_id=demandeur.id,
                statut=StatutDemandeAdhesion.EN_ATTENTE,
            )
            s.add(demande); s.commit(); s.refresh(demande)

            return engine, admin.id, createur.id, demandeur.id, cercle.id, demande.id

    def test_createur_refuse_si_le_profil_a_change(self):
        engine, _, createur_id, demandeur_id, cercle_id, demande_id = self._fixture()
        with Session(engine) as s:
            resultat = _traiter_acceptation_demande(
                s,
                s.get(CercleEtude, cercle_id),
                s.get(DemandeAdhesionCercle, demande_id),
                s.get(Utilisateur, createur_id),
                force_admin=False,
            )
            self.assertEqual(resultat, "profil_change")
            demande = s.get(DemandeAdhesionCercle, demande_id)
            self.assertEqual(demande.statut, StatutDemandeAdhesion.REJETEE)

    def test_admin_peut_accepter_malgre_changement_de_profil(self):
        engine, admin_id, _, demandeur_id, cercle_id, demande_id = self._fixture()
        with Session(engine) as s:
            resultat = _traiter_acceptation_demande(
                s,
                s.get(CercleEtude, cercle_id),
                s.get(DemandeAdhesionCercle, demande_id),
                s.get(Utilisateur, admin_id),
                force_admin=True,
            )
            self.assertIsNone(resultat)
            demande = s.get(DemandeAdhesionCercle, demande_id)
            self.assertEqual(demande.statut, StatutDemandeAdhesion.ACCEPTEE)
            membre = s.exec(
                __import__("sqlmodel", fromlist=["select"]).select(MembreCercle).where(
                    MembreCercle.cercle_id == cercle_id,
                    MembreCercle.utilisateur_id == demandeur_id,
                )
            ).first()
            self.assertIsNotNone(membre)

if __name__ == "__main__":
    unittest.main()
