"""
Teste la logique metier du workflow "demande de creation de cercle
national" au niveau ORM (independant de FastAPI/HTTP), en reproduisant
exactement ce que font les routes de admin_referentiel_router.py.

Lancer avec :
    python -m unittest tests.test_demande_creation_cercle -v
"""
import unittest
from datetime import datetime

from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

from app.models import (
    Universite, Faculte, Mention, Filiere, CercleEtude, MembreCercle, RoleMembreCercle,
    StatutCercle, Utilisateur, RoleUtilisateur, DemandeCreationCercle, StatutDemandeCreationCercle,
)


def _nouvel_engine_sqlite():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _activer_fk(connexion_dbapi, _record):
        connexion_dbapi.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine


def _approuver(session: Session, demande: DemandeCreationCercle, admin_id: int) -> CercleEtude:
    """Reproduit exactement la logique de approuver_demande_creation()."""
    doublon = session.exec(
        select(CercleEtude).where(
            CercleEtude.mention_id == demande.mention_id,
            CercleEtude.filiere_id == demande.filiere_id,
            CercleEtude.niveau == demande.niveau,
            CercleEtude.statut == StatutCercle.ACTIF,
        )
    ).first()
    if doublon:
        demande.statut = StatutDemandeCreationCercle.REJETEE
        demande.date_traitement = datetime.utcnow()
        demande.traite_par_id = admin_id
        demande.cercle_cree_id = doublon.id
        session.add(demande)
        session.commit()
        return doublon

    cercle = CercleEtude(
        nom=demande.nom, description=demande.description,
        mention_id=demande.mention_id, filiere_id=demande.filiere_id, niveau=demande.niveau,
        statut=StatutCercle.ACTIF, createur_id=demande.utilisateur_id,
    )
    session.add(cercle); session.commit(); session.refresh(cercle)
    session.add(MembreCercle(cercle_id=cercle.id, utilisateur_id=demande.utilisateur_id, role=RoleMembreCercle.CREATEUR))
    demande.statut = StatutDemandeCreationCercle.APPROUVEE
    demande.date_traitement = datetime.utcnow()
    demande.traite_par_id = admin_id
    demande.cercle_cree_id = cercle.id
    session.add(demande)
    session.commit()
    return cercle


class TestDemandeCreationCercle(unittest.TestCase):

    def setUp(self):
        self.engine = _nouvel_engine_sqlite()
        with Session(self.engine) as session:
            universite = Universite(nom="Universite de Toamasina")
            session.add(universite); session.commit(); session.refresh(universite)
            faculte = Faculte(nom="DEGMIA", universite_id=universite.id)
            session.add(faculte); session.commit(); session.refresh(faculte)
            mention = Mention(nom="Sciences de Gestion")
            session.add(mention); session.commit(); session.refresh(mention)
            self.mention_id = mention.id
            filiere = Filiere(nom="Finance et Comptabilite", faculte_id=faculte.id, mention_id=mention.id)
            session.add(filiere); session.commit(); session.refresh(filiere)
            self.filiere_id = filiere.id

            etudiant = Utilisateur(nom="Jake", telephone="0340000001", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT)
            session.add(etudiant); session.commit(); session.refresh(etudiant)
            self.etudiant_id = etudiant.id
            admin = Utilisateur(nom="Admin", telephone="0340000002", mot_de_passe_hash="x", role=RoleUtilisateur.ADMIN)
            session.add(admin); session.commit(); session.refresh(admin)
            self.admin_id = admin.id

    def test_approbation_cree_le_cercle_avec_createur(self):
        with Session(self.engine) as session:
            demande = DemandeCreationCercle(
                utilisateur_id=self.etudiant_id, mention_id=self.mention_id, filiere_id=self.filiere_id,
                niveau="L3", nom="Finance L3", raison="Plusieurs etudiants de plusieurs universites le demandent.",
            )
            session.add(demande); session.commit(); session.refresh(demande)

            resultat = _approuver(session, demande, self.admin_id)
            self.assertEqual(resultat.statut, StatutCercle.ACTIF)
            self.assertEqual(resultat.mention_id, self.mention_id)
            self.assertEqual(resultat.niveau, "L3")

            membre = session.exec(
                select(MembreCercle).where(MembreCercle.cercle_id == resultat.id, MembreCercle.utilisateur_id == self.etudiant_id)
            ).first()
            self.assertIsNotNone(membre)
            self.assertEqual(membre.role, RoleMembreCercle.CREATEUR)

            demande_rechargee = session.get(DemandeCreationCercle, demande.id)
            self.assertEqual(demande_rechargee.statut, StatutDemandeCreationCercle.APPROUVEE)
            self.assertEqual(demande_rechargee.cercle_cree_id, resultat.id)

    def test_rejet_ne_cree_aucun_cercle(self):
        with Session(self.engine) as session:
            demande = DemandeCreationCercle(
                utilisateur_id=self.etudiant_id, mention_id=self.mention_id, filiere_id=self.filiere_id,
                niveau="L2", nom="Finance L2", raison="Raison quelconque.",
            )
            session.add(demande); session.commit(); session.refresh(demande)

            demande.statut = StatutDemandeCreationCercle.REJETEE
            demande.date_traitement = datetime.utcnow()
            demande.traite_par_id = self.admin_id
            session.add(demande); session.commit()

            cercles = session.exec(select(CercleEtude)).all()
            self.assertEqual(len(cercles), 0)

    def test_doublon_survenu_entre_temps_rejette_automatiquement(self):
        """§32 du brief, applique ici au workflow de creation : si un
        cercle equivalent existe deja au moment de l'approbation (cree
        entre-temps par une autre demande approuvee en premier), la
        demande est automatiquement rejetee plutot que de creer un
        doublon."""
        with Session(self.engine) as session:
            # Un cercle existe deja pour cette combinaison exacte.
            cercle_existant = CercleEtude(
                nom="Deja la", mention_id=self.mention_id, filiere_id=self.filiere_id,
                niveau="L3", statut=StatutCercle.ACTIF, createur_id=self.etudiant_id,
            )
            session.add(cercle_existant); session.commit(); session.refresh(cercle_existant)

            demande = DemandeCreationCercle(
                utilisateur_id=self.etudiant_id, mention_id=self.mention_id, filiere_id=self.filiere_id,
                niveau="L3", nom="Encore un autre nom", raison="Raison quelconque.",
            )
            session.add(demande); session.commit(); session.refresh(demande)

            resultat = _approuver(session, demande, self.admin_id)
            self.assertEqual(resultat.id, cercle_existant.id)  # renvoie l'existant, n'en cree pas un 2e

            demande_rechargee = session.get(DemandeCreationCercle, demande.id)
            self.assertEqual(demande_rechargee.statut, StatutDemandeCreationCercle.REJETEE)

            cercles = session.exec(select(CercleEtude)).all()
            self.assertEqual(len(cercles), 1, "Un seul cercle doit exister, pas de doublon cree")


if __name__ == "__main__":
    unittest.main()
