"""
Teste app/referentiel_academique.py de maniere isolee (pas de FastAPI,
juste SQLModel + la logique pure).

Lancer avec :
    python -m unittest tests.test_referentiel_academique -v
"""
import unittest
from datetime import datetime, timedelta

from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine

from app.models import Universite, Faculte, Mention, Filiere, CercleEtude, Utilisateur, RoleUtilisateur
from app.referentiel_academique import (
    cercle_est_national,
    peut_modifier_niveau_maintenant,
    jours_avant_prochain_changement_niveau,
    prochain_changement_niveau_autorise_le,
    profil_correspond_au_cercle,
)


def _nouvel_engine_sqlite():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _activer_fk(connexion_dbapi, _record):
        connexion_dbapi.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine


class TestCooldownNiveau(unittest.TestCase):

    def test_jamais_modifie_peut_changer_immediatement(self):
        u = Utilisateur(nom="Jake", telephone="034", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT)
        self.assertTrue(peut_modifier_niveau_maintenant(u))
        self.assertIsNone(prochain_changement_niveau_autorise_le(u))
        self.assertEqual(jours_avant_prochain_changement_niveau(u), 0)

    def test_modifie_il_y_a_2_jours_ne_peut_pas_changer(self):
        u = Utilisateur(
            nom="Jake", telephone="034", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT,
            niveau_modifie_le=datetime.utcnow() - timedelta(days=2),
        )
        self.assertFalse(peut_modifier_niveau_maintenant(u))
        self.assertGreater(jours_avant_prochain_changement_niveau(u), 0)

    def test_modifie_il_y_a_exactement_14_jours_peut_changer(self):
        u = Utilisateur(
            nom="Jake", telephone="034", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT,
            niveau_modifie_le=datetime.utcnow() - timedelta(days=14, minutes=1),
        )
        self.assertTrue(peut_modifier_niveau_maintenant(u))

    def test_modifie_il_y_a_13_jours_ne_peut_pas_encore(self):
        u = Utilisateur(
            nom="Jake", telephone="034", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT,
            niveau_modifie_le=datetime.utcnow() - timedelta(days=13),
        )
        self.assertFalse(peut_modifier_niveau_maintenant(u))
        self.assertEqual(jours_avant_prochain_changement_niveau(u), 1)

    def test_15_aout_plus_14_jours_donne_29_aout(self):
        """Exemple exact du brief : 15 aout L1->L2, prochain changement
        autorise le 29 aout ou apres."""
        u = Utilisateur(
            nom="Jake", telephone="034", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT,
            niveau="L2", niveau_modifie_le=datetime(2026, 8, 15, 10, 0, 0),
        )
        echeance = prochain_changement_niveau_autorise_le(u)
        self.assertEqual(echeance, datetime(2026, 8, 29, 10, 0, 0))


class TestCorrespondanceCercle(unittest.TestCase):

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

            autre_mention = Mention(nom="Droit")
            session.add(autre_mention); session.commit(); session.refresh(autre_mention)
            autre_filiere = Filiere(nom="Droit prive", faculte_id=faculte.id, mention_id=autre_mention.id)
            session.add(autre_filiere); session.commit(); session.refresh(autre_filiere)
            self.autre_filiere_id = autre_filiere.id

            createur = Utilisateur(nom="Createur", telephone="0340000001", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT)
            session.add(createur); session.commit(); session.refresh(createur)
            self.createur_id = createur.id

    def test_cercle_libre_accepte_tout_le_monde(self):
        with Session(self.engine) as session:
            cercle = CercleEtude(nom="Groupe libre", createur_id=self.createur_id)
            self.assertFalse(cercle_est_national(cercle))
            u = Utilisateur(nom="X", telephone="0340000002", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT)
            self.assertTrue(profil_correspond_au_cercle(u, cercle, session))

    def test_utilisateur_meme_mention_filiere_niveau_correspond(self):
        with Session(self.engine) as session:
            cercle = CercleEtude(
                nom="Finance L3", createur_id=self.createur_id,
                mention_id=self.mention_id, filiere_id=self.filiere_id, niveau="L3",
            )
            self.assertTrue(cercle_est_national(cercle))
            u = Utilisateur(nom="X", telephone="0340000003", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT,
                             filiere_id=self.filiere_id, niveau="L3")
            self.assertTrue(profil_correspond_au_cercle(u, cercle, session))

    def test_utilisateur_niveau_different_ne_correspond_pas(self):
        """Exemple exact du brief §31 : L1 ne peut pas rejoindre L2."""
        with Session(self.engine) as session:
            cercle = CercleEtude(
                nom="Finance L2", createur_id=self.createur_id,
                mention_id=self.mention_id, filiere_id=self.filiere_id, niveau="L2",
            )
            u = Utilisateur(nom="X", telephone="0340000004", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT,
                             filiere_id=self.filiere_id, niveau="L1")
            self.assertFalse(profil_correspond_au_cercle(u, cercle, session))

    def test_utilisateur_autre_filiere_ne_correspond_pas(self):
        with Session(self.engine) as session:
            cercle = CercleEtude(
                nom="Finance L3", createur_id=self.createur_id,
                mention_id=self.mention_id, filiere_id=self.filiere_id, niveau="L3",
            )
            u = Utilisateur(nom="X", telephone="0340000005", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT,
                             filiere_id=self.autre_filiere_id, niveau="L3")
            self.assertFalse(profil_correspond_au_cercle(u, cercle, session))

    def test_utilisateur_sans_filiere_ne_correspond_a_aucun_cercle_national(self):
        with Session(self.engine) as session:
            cercle = CercleEtude(
                nom="Finance L3", createur_id=self.createur_id,
                mention_id=self.mention_id, filiere_id=self.filiere_id, niveau="L3",
            )
            u = Utilisateur(nom="X", telephone="0340000006", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT)
            self.assertFalse(profil_correspond_au_cercle(u, cercle, session))


if __name__ == "__main__":
    unittest.main()
