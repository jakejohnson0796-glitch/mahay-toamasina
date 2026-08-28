"""
Teste la logique metier partagee d'acceptation/refus d'une
DemandeAdhesionCercle (_traiter_acceptation_demande / _traiter_refus_demande
dans app/routers/cercles_router.py), utilisee a la fois par la page de
gestion d'un cercle (createur/admin) et par la nouvelle liste globale
admin (/admin/demandes-adhesion). Avant ce correctif, aucune de ces deux
fonctions (ni le flux d'adhesion en general) n'avait de test.

Lancer avec :
    python -m unittest tests.test_demandes_adhesion_cercle -v
"""
import unittest
from datetime import datetime

from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

from app.models import (
    Universite, Faculte, Mention, Filiere, CercleEtude, MembreCercle, StatutCercle,
    Utilisateur, RoleUtilisateur, DemandeAdhesionCercle, StatutDemandeAdhesion,
)
from app.routers.cercles_router import _traiter_acceptation_demande, _traiter_refus_demande


def _nouvel_engine_sqlite():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _activer_fk(connexion_dbapi, _record):
        connexion_dbapi.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine


class TestDemandesAdhesionCercle(unittest.TestCase):

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
            autre_filiere = Filiere(nom="Marketing", faculte_id=faculte.id, mention_id=mention.id)
            session.add(autre_filiere); session.commit(); session.refresh(autre_filiere)
            self.autre_filiere_id = autre_filiere.id

            etudiant = Utilisateur(
                nom="Jake", telephone="0340000001", mot_de_passe_hash="x",
                role=RoleUtilisateur.ETUDIANT, filiere_id=self.filiere_id, niveau="L3",
            )
            session.add(etudiant); session.commit(); session.refresh(etudiant)
            self.etudiant_id = etudiant.id
            admin = Utilisateur(nom="Admin", telephone="0340000002", mot_de_passe_hash="x", role=RoleUtilisateur.ADMIN)
            session.add(admin); session.commit(); session.refresh(admin)
            self.admin_id = admin.id

            # Cercle "libre" (pas national) : aucune restriction de profil.
            cercle_libre = CercleEtude(nom="Cercle libre", statut=StatutCercle.ACTIF, createur_id=self.etudiant_id)
            session.add(cercle_libre); session.commit(); session.refresh(cercle_libre)
            self.cercle_libre_id = cercle_libre.id

            # Cercle national qui correspond exactement au profil de l'etudiant.
            cercle_national = CercleEtude(
                nom="Finance L3", mention_id=self.mention_id, filiere_id=self.filiere_id, niveau="L3",
                statut=StatutCercle.ACTIF, createur_id=self.admin_id,
            )
            session.add(cercle_national); session.commit(); session.refresh(cercle_national)
            self.cercle_national_id = cercle_national.id

            # Cercle national d'un AUTRE parcours (ne correspond pas au profil de l'etudiant).
            cercle_autre_parcours = CercleEtude(
                nom="Marketing L3", mention_id=self.mention_id, filiere_id=self.autre_filiere_id, niveau="L3",
                statut=StatutCercle.ACTIF, createur_id=self.admin_id,
            )
            session.add(cercle_autre_parcours); session.commit(); session.refresh(cercle_autre_parcours)
            self.cercle_autre_parcours_id = cercle_autre_parcours.id

    def _creer_demande(self, session: Session, cercle_id: int) -> DemandeAdhesionCercle:
        demande = DemandeAdhesionCercle(cercle_id=cercle_id, utilisateur_id=self.etudiant_id, raison="Je veux echanger sur les revisions.")
        session.add(demande); session.commit(); session.refresh(demande)
        return demande

    def test_acceptation_ajoute_le_membre(self):
        with Session(self.engine) as session:
            admin = session.get(Utilisateur, self.admin_id)
            cercle = session.get(CercleEtude, self.cercle_libre_id)
            demande = self._creer_demande(session, self.cercle_libre_id)

            resultat = _traiter_acceptation_demande(session, cercle, demande, admin)
            self.assertIsNone(resultat)

            demande_rechargee = session.get(DemandeAdhesionCercle, demande.id)
            self.assertEqual(demande_rechargee.statut, StatutDemandeAdhesion.ACCEPTEE)
            self.assertEqual(demande_rechargee.traite_par_id, self.admin_id)
            self.assertIsNotNone(demande_rechargee.date_traitement)

            membre = session.exec(
                select(MembreCercle).where(
                    MembreCercle.cercle_id == self.cercle_libre_id, MembreCercle.utilisateur_id == self.etudiant_id
                )
            ).first()
            self.assertIsNotNone(membre)

    def test_acceptation_sur_cercle_national_compatible(self):
        with Session(self.engine) as session:
            admin = session.get(Utilisateur, self.admin_id)
            cercle = session.get(CercleEtude, self.cercle_national_id)
            demande = self._creer_demande(session, self.cercle_national_id)

            resultat = _traiter_acceptation_demande(session, cercle, demande, admin)
            self.assertIsNone(resultat)
            self.assertEqual(session.get(DemandeAdhesionCercle, demande.id).statut, StatutDemandeAdhesion.ACCEPTEE)

    def test_acceptation_refusee_si_profil_ne_correspond_plus(self):
        """§32 du brief : si le profil du demandeur a change (ou ne
        correspondait deja plus) entre la demande et son traitement, la
        demande est automatiquement rejetee plutot qu'acceptee dans le
        mauvais cercle national."""
        with Session(self.engine) as session:
            admin = session.get(Utilisateur, self.admin_id)
            cercle = session.get(CercleEtude, self.cercle_autre_parcours_id)
            demande = self._creer_demande(session, self.cercle_autre_parcours_id)

            resultat = _traiter_acceptation_demande(session, cercle, demande, admin)
            self.assertEqual(resultat, "profil_change")

            demande_rechargee = session.get(DemandeAdhesionCercle, demande.id)
            self.assertEqual(demande_rechargee.statut, StatutDemandeAdhesion.REJETEE)

            membre = session.exec(
                select(MembreCercle).where(
                    MembreCercle.cercle_id == self.cercle_autre_parcours_id, MembreCercle.utilisateur_id == self.etudiant_id
                )
            ).first()
            self.assertIsNone(membre, "Aucun membre ne doit etre ajoute quand le profil ne correspond plus")

    def test_refus_marque_rejetee_sans_ajouter_de_membre(self):
        with Session(self.engine) as session:
            admin = session.get(Utilisateur, self.admin_id)
            demande = self._creer_demande(session, self.cercle_libre_id)

            _traiter_refus_demande(session, demande, admin)

            demande_rechargee = session.get(DemandeAdhesionCercle, demande.id)
            self.assertEqual(demande_rechargee.statut, StatutDemandeAdhesion.REJETEE)
            self.assertEqual(demande_rechargee.traite_par_id, self.admin_id)

            membre = session.exec(
                select(MembreCercle).where(
                    MembreCercle.cercle_id == self.cercle_libre_id, MembreCercle.utilisateur_id == self.etudiant_id
                )
            ).first()
            self.assertIsNone(membre)

    def test_demande_deja_traitee_ne_peut_pas_etre_retraitee(self):
        """Double-clic / action concurrente : une demande deja ACCEPTEE
        (ou REJETEE) ne doit plus bouger, ni cote statut ni cote
        adhesion — evite d'ajouter deux fois le membre ou d'ecraser une
        decision deja prise."""
        with Session(self.engine) as session:
            admin = session.get(Utilisateur, self.admin_id)
            cercle = session.get(CercleEtude, self.cercle_libre_id)
            demande = self._creer_demande(session, self.cercle_libre_id)

            premier_resultat = _traiter_acceptation_demande(session, cercle, demande, admin)
            self.assertIsNone(premier_resultat)

            demande_rechargee = session.get(DemandeAdhesionCercle, demande.id)
            second_resultat = _traiter_acceptation_demande(session, cercle, demande_rechargee, admin)
            self.assertEqual(second_resultat, "deja_traitee")

            membres = session.exec(
                select(MembreCercle).where(
                    MembreCercle.cercle_id == self.cercle_libre_id, MembreCercle.utilisateur_id == self.etudiant_id
                )
            ).all()
            self.assertEqual(len(membres), 1, "Le membre ne doit pas etre ajoute deux fois")

    def test_liste_globale_regroupe_les_demandes_de_plusieurs_cercles(self):
        """Reproduit la requete de page_demandes_adhesion()
        (admin_router.py) : verifie qu'une demande EN_ATTENTE sur
        n'importe quel cercle apparait dans la liste globale, et
        qu'une demande deja traitee en est exclue."""
        with Session(self.engine) as session:
            demande_libre = self._creer_demande(session, self.cercle_libre_id)
            demande_nationale = self._creer_demande(session, self.cercle_national_id)
            demande_traitee = self._creer_demande(session, self.cercle_autre_parcours_id)
            demande_traitee.statut = StatutDemandeAdhesion.REJETEE
            demande_traitee.date_traitement = datetime.utcnow()
            session.add(demande_traitee); session.commit()

            lignes = session.exec(
                select(DemandeAdhesionCercle, Utilisateur, CercleEtude)
                .where(DemandeAdhesionCercle.statut == StatutDemandeAdhesion.EN_ATTENTE)
                .where(DemandeAdhesionCercle.utilisateur_id == Utilisateur.id)
                .where(DemandeAdhesionCercle.cercle_id == CercleEtude.id)
                .order_by(DemandeAdhesionCercle.date_creation)
            ).all()

            ids_en_attente = {d.id for d, _, _ in lignes}
            self.assertIn(demande_libre.id, ids_en_attente)
            self.assertIn(demande_nationale.id, ids_en_attente)
            self.assertNotIn(demande_traitee.id, ids_en_attente)
            self.assertEqual(len(lignes), 2, "Deux cercles differents, deux demandes en attente")


if __name__ == "__main__":
    unittest.main()
