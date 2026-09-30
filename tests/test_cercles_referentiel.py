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
    RoleUtilisateur, StatutCercle, Universite, Utilisateur, ProgrammeUniversitaire,
)
from app.referentiel import NIVEAUX
from app.referentiel_academique import filiere_canonique_pour_cercle


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
            self.universite_id = universite.id

            mention = Mention(nom="Informatique")
            session.add(mention); session.commit(); session.refresh(mention)
            self.mention_id = mention.id

    def test_parcours_equivalent_utilise_une_filiere_representante_unique(self):
        with Session(self.engine) as session:
            f1 = Filiere(
                nom="Commerce International",
                faculte_id=self.faculte_id,
                mention_id=self.mention_id,
                niveau="M1",
            )
            session.add(f1); session.commit(); session.refresh(f1)
            session.add(ProgrammeUniversitaire(
                universite_id=self.universite_id,
                filiere_id=f1.id,
                est_active=True,
            ))

            autre_univ = Universite(nom="Universite Autre")
            session.add(autre_univ); session.commit(); session.refresh(autre_univ)
            autre_fac = Faculte(nom="Sciences", universite_id=autre_univ.id)
            session.add(autre_fac); session.commit(); session.refresh(autre_fac)
            f2 = Filiere(
                nom="Commerce International ",
                faculte_id=autre_fac.id,
                mention_id=self.mention_id,
                niveau="M1",
            )
            session.add(f2); session.commit(); session.refresh(f2)
            session.add(ProgrammeUniversitaire(
                universite_id=autre_univ.id,
                filiere_id=f2.id,
                est_active=True,
            ))
            session.commit()

            canon1 = filiere_canonique_pour_cercle(session, f1)
            canon2 = filiere_canonique_pour_cercle(session, f2)
            self.assertEqual(canon1.id, canon2.id)
            self.assertEqual(canon1.id, min(f1.id, f2.id))

    def test_cree_un_cercle_pour_le_niveau_verifie_dune_filiere(self):
        with Session(self.engine) as session:
            filiere = Filiere(nom="Info Generale", faculte_id=self.faculte_id, mention_id=self.mention_id, niveau="L3")
            session.add(filiere); session.commit(); session.refresh(filiere)
            session.add(ProgrammeUniversitaire(
                universite_id=self.universite_id,
                filiere_id=filiere.id,
                est_active=True,
            ))
            session.commit()

            total = assurer_cercles_referentiel(session)
            self.assertEqual(total, 1)

            cercles = session.exec(select(CercleEtude)).all()
            self.assertEqual(len(cercles), 1)
            self.assertEqual({c.niveau for c in cercles}, {"L3"})
            for c in cercles:
                self.assertEqual(c.mention_id, self.mention_id)
                self.assertEqual(c.filiere_id, filiere.id)
                self.assertEqual(c.statut, StatutCercle.ACTIF)

    def test_deux_filieres_equivalentes_ne_creent_quun_cercle_national(self):
        with Session(self.engine) as session:
            autre_universite = Universite(nom="Universite de Test 2")
            session.add(autre_universite); session.commit(); session.refresh(autre_universite)
            autre_faculte = Faculte(nom="Sciences 2", universite_id=autre_universite.id)
            session.add(autre_faculte); session.commit(); session.refresh(autre_faculte)

            f1 = Filiere(
                nom="Genie Informatique",
                faculte_id=self.faculte_id,
                mention_id=self.mention_id,
                niveau="M1",
            )
            f2 = Filiere(
                nom="Génie Informatique",
                faculte_id=autre_faculte.id,
                mention_id=self.mention_id,
                niveau="M1",
            )
            session.add(f1); session.add(f2); session.commit()
            session.refresh(f1); session.refresh(f2)
            session.add(ProgrammeUniversitaire(
                universite_id=self.universite_id,
                filiere_id=f1.id,
                est_active=True,
            ))
            session.add(ProgrammeUniversitaire(
                universite_id=autre_universite.id,
                filiere_id=f2.id,
                est_active=True,
            ))
            session.commit()

            total = assurer_cercles_referentiel(session)
            cercles = session.exec(
                select(CercleEtude).where(
                    CercleEtude.mention_id == self.mention_id,
                    CercleEtude.niveau == "M1",
                    CercleEtude.statut == StatutCercle.ACTIF,
                )
            ).all()
            self.assertEqual(total, 1)
            self.assertEqual(len(cercles), 1)
            self.assertIn(cercles[0].filiere_id, {f1.id, f2.id})

    def test_tronc_commun_source_cree_un_seul_cercle_par_mention_niveau(self):
        with Session(self.engine) as session:
            f = Filiere(
                nom="Informatique Parcours M1",
                faculte_id=self.faculte_id,
                mention_id=self.mention_id,
                niveau="M1",
            )
            session.add(f); session.commit(); session.refresh(f)
            session.add(ProgrammeUniversitaire(
                universite_id=self.universite_id,
                filiere_id=f.id,
                est_active=True,
            ))
            session.commit()

            total = assurer_cercles_referentiel(
                session,
                identites_tronc={(self.mention_id, "L1"), (self.mention_id, "L2")},
            )
            self.assertEqual(total, 3)
            troncs = session.exec(
                select(CercleEtude).where(
                    CercleEtude.mention_id == self.mention_id,
                    CercleEtude.filiere_id.is_(None),
                    CercleEtude.statut == StatutCercle.ACTIF,
                )
            ).all()
            self.assertEqual({c.niveau for c in troncs}, {"L1", "L2"})

    def test_filiere_sans_mention_ignoree(self):
        with Session(self.engine) as session:
            session.add(Filiere(nom="Sans mention", faculte_id=self.faculte_id))
            session.commit()

            total = assurer_cercles_referentiel(session)
            self.assertEqual(total, 0)
            self.assertEqual(len(session.exec(select(CercleEtude)).all()), 0)

    def test_idempotent_deuxieme_appel_ne_recree_rien(self):
        with Session(self.engine) as session:
            filiere = Filiere(nom="Info Generale", faculte_id=self.faculte_id, mention_id=self.mention_id, niveau="L3")
            session.add(filiere); session.commit(); session.refresh(filiere)
            session.add(ProgrammeUniversitaire(
                universite_id=self.universite_id,
                filiere_id=filiere.id,
                est_active=True,
            ))
            session.commit()

            assurer_cercles_referentiel(session)
            total_second_appel = assurer_cercles_referentiel(session)

            self.assertEqual(total_second_appel, 0)
            self.assertEqual(len(session.exec(select(CercleEtude)).all()), 1)

    def test_cercle_deja_cree_manuellement_pour_un_niveau_nest_pas_duplique(self):
        """Si un cercle national existe deja pour un niveau donne (cree
        via l'ancien workflow de demande/approbation), le provisionnement
        automatique ne doit generer que les 7 niveaux restants."""
        with Session(self.engine) as session:
            filiere = Filiere(nom="Info Generale", faculte_id=self.faculte_id, mention_id=self.mention_id, niveau="L3")
            session.add(filiere); session.commit(); session.refresh(filiere)
            session.add(ProgrammeUniversitaire(
                universite_id=self.universite_id,
                filiere_id=filiere.id,
                est_active=True,
            ))
            session.commit()

            session.add(CercleEtude(
                nom="Info Generale — Licence 3 (deja existant)",
                createur_id=self.admin_id,
                mention_id=self.mention_id, filiere_id=filiere.id, niveau="L3",
                statut=StatutCercle.ACTIF,
            ))
            session.commit()

            total = assurer_cercles_referentiel(session)
            self.assertEqual(total, 0)
            self.assertEqual(len(session.exec(select(CercleEtude)).all()), 1)

    def test_createur_devient_membre_avec_role_createur(self):
        with Session(self.engine) as session:
            filiere = Filiere(nom="Info Generale", faculte_id=self.faculte_id, mention_id=self.mention_id, niveau="L3")
            session.add(filiere); session.commit(); session.refresh(filiere)
            session.add(ProgrammeUniversitaire(
                universite_id=self.universite_id,
                filiere_id=filiere.id,
                est_active=True,
            ))
            session.commit()

            admin = session.get(Utilisateur, self.admin_id)
            assurer_cercles_pour_filiere(session, filiere, admin)

            membres = session.exec(
                select(MembreCercle).where(MembreCercle.utilisateur_id == self.admin_id)
            ).all()
            self.assertEqual(len(membres), 1)
            for m in membres:
                self.assertEqual(m.role, RoleMembreCercle.CREATEUR)

    def test_sans_admin_ne_leve_pas_et_ne_cree_rien(self):
        """Aucun compte admin en base -> provisionnement simplement
        reporte (createur_id requis, pas nullable sur CercleEtude)."""
        with Session(self.engine) as session:
            for m in session.exec(select(Utilisateur)).all():
                session.delete(m)
            session.commit()

            filiere = Filiere(nom="Info Generale", faculte_id=self.faculte_id, mention_id=self.mention_id, niveau="L3")
            session.add(filiere); session.commit(); session.refresh(filiere)
            session.add(ProgrammeUniversitaire(
                universite_id=self.universite_id,
                filiere_id=filiere.id,
                est_active=True,
            ))
            session.commit()

            total = assurer_cercles_referentiel(session)
            self.assertEqual(total, 0)
            self.assertEqual(len(session.exec(select(CercleEtude)).all()), 0)


if __name__ == "__main__":
    unittest.main()
