"""
Verifie le provisionnement automatique des cercles nationaux
(app/cercles_referentiel.py) : un cercle par (mention, filiere,
niveau) pour chaque filiere deja rattachee a une mention, sans
attendre qu'un etudiant en demande un explicitement.

Lancer avec :
    python -m unittest tests.test_cercles_referentiel -v
"""
import unittest

from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

from app.cercles_referentiel import assurer_cercles_pour_filiere, assurer_cercles_referentiel
from app.models import (
    CercleEtude, Faculte, Filiere, MembreCercle, Mention, RoleMembreCercle,
    RoleUtilisateur, StatutCercle, Universite, Utilisateur,
)
from app.referentiel import NIVEAUX


def _nouvel_engine_sqlite():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _activer_fk(connexion_dbapi, _record):
        connexion_dbapi.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine


class TestCerclesReferentiel(unittest.TestCase):

    def setUp(self):
        self.engine = _nouvel_engine_sqlite()
        with Session(self.engine) as session:
            admin = Utilisateur(nom="Admin", telephone="0340000001", mot_de_passe_hash="x", role=RoleUtilisateur.ADMIN)
            session.add(admin); session.commit(); session.refresh(admin)
            self.admin_id = admin.id

            universite = Universite(nom="Universite de Toamasina")
            session.add(universite); session.commit(); session.refresh(universite)

            faculte = Faculte(nom="Sciences", universite_id=universite.id)
            session.add(faculte); session.commit(); session.refresh(faculte)
            self.faculte_id = faculte.id

            mention = Mention(nom="Informatique")
            session.add(mention); session.commit(); session.refresh(mention)
            self.mention_id = mention.id

    def test_cree_un_cercle_par_niveau_pour_une_filiere_avec_mention(self):
        with Session(self.engine) as session:
            filiere = Filiere(nom="Info Generale", faculte_id=self.faculte_id, mention_id=self.mention_id)
            session.add(filiere); session.commit(); session.refresh(filiere)

            total = assurer_cercles_referentiel(session)
            self.assertEqual(total, len(NIVEAUX))

            cercles = session.exec(select(CercleEtude)).all()
            self.assertEqual(len(cercles), len(NIVEAUX))
            self.assertEqual({c.niveau for c in cercles}, set(NIVEAUX))
            for c in cercles:
                self.assertEqual(c.mention_id, self.mention_id)
                self.assertEqual(c.filiere_id, filiere.id)
                self.assertEqual(c.statut, StatutCercle.ACTIF)

    def test_filiere_sans_mention_ignoree(self):
        with Session(self.engine) as session:
            session.add(Filiere(nom="Sans mention", faculte_id=self.faculte_id))
            session.commit()

            total = assurer_cercles_referentiel(session)
            self.assertEqual(total, 0)
            self.assertEqual(len(session.exec(select(CercleEtude)).all()), 0)

    def test_idempotent_deuxieme_appel_ne_recree_rien(self):
        with Session(self.engine) as session:
            filiere = Filiere(nom="Info Generale", faculte_id=self.faculte_id, mention_id=self.mention_id)
            session.add(filiere); session.commit()

            assurer_cercles_referentiel(session)
            total_second_appel = assurer_cercles_referentiel(session)

            self.assertEqual(total_second_appel, 0)
            self.assertEqual(len(session.exec(select(CercleEtude)).all()), len(NIVEAUX))

    def test_cercle_deja_cree_manuellement_pour_un_niveau_nest_pas_duplique(self):
        """Si un cercle national existe deja pour un niveau donne (cree
        via l'ancien workflow de demande/approbation), le provisionnement
        automatique ne doit generer que les 7 niveaux restants."""
        with Session(self.engine) as session:
            filiere = Filiere(nom="Info Generale", faculte_id=self.faculte_id, mention_id=self.mention_id)
            session.add(filiere); session.commit(); session.refresh(filiere)

            session.add(CercleEtude(
                nom="Info Generale — Licence 3 (deja existant)",
                createur_id=self.admin_id,
                mention_id=self.mention_id, filiere_id=filiere.id, niveau="L3",
                statut=StatutCercle.ACTIF,
            ))
            session.commit()

            total = assurer_cercles_referentiel(session)
            self.assertEqual(total, len(NIVEAUX) - 1)
            self.assertEqual(len(session.exec(select(CercleEtude)).all()), len(NIVEAUX))

    def test_createur_devient_membre_avec_role_createur(self):
        with Session(self.engine) as session:
            filiere = Filiere(nom="Info Generale", faculte_id=self.faculte_id, mention_id=self.mention_id)
            session.add(filiere); session.commit(); session.refresh(filiere)

            admin = session.get(Utilisateur, self.admin_id)
            assurer_cercles_pour_filiere(session, filiere, admin)

            membres = session.exec(
                select(MembreCercle).where(MembreCercle.utilisateur_id == self.admin_id)
            ).all()
            self.assertEqual(len(membres), len(NIVEAUX))
            for m in membres:
                self.assertEqual(m.role, RoleMembreCercle.CREATEUR)

    def test_sans_admin_ne_leve_pas_et_ne_cree_rien(self):
        """Aucun compte admin en base -> provisionnement simplement
        reporte (createur_id requis, pas nullable sur CercleEtude)."""
        with Session(self.engine) as session:
            for m in session.exec(select(Utilisateur)).all():
                session.delete(m)
            session.commit()

            filiere = Filiere(nom="Info Generale", faculte_id=self.faculte_id, mention_id=self.mention_id)
            session.add(filiere); session.commit()

            total = assurer_cercles_referentiel(session)
            self.assertEqual(total, 0)
            self.assertEqual(len(session.exec(select(CercleEtude)).all()), 0)


if __name__ == "__main__":
    unittest.main()
