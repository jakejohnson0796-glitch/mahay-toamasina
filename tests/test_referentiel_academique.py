"""
Teste app/referentiel_academique.py de maniere isolee (pas de FastAPI,
juste SQLModel + la logique pure).

Lancer avec :
    python -m unittest tests.test_referentiel_academique -v
"""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

from app.models import Universite, Faculte, Mention, Filiere, CercleEtude, Utilisateur, RoleUtilisateur
from app.referentiel_academique import (
    cercle_est_national,
    peut_modifier_niveau_maintenant,
    jours_avant_prochain_changement_niveau,
    prochain_changement_niveau_autorise_le,
    profil_correspond_au_cercle,
    condition_cercles_disponibles,
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
        autorise le 29 aout ou apres.

        "Maintenant" est fige a une date interieure a la fenetre de
        cooldown (20 aout, avant l'echeance du 29) plutot que de
        dependre de la vraie date d'execution du test — sans ca, ce
        test ne pouvait passer que les jours precedant le 29 aout 2026
        et echouait mecaniquement a partir de cette date-la (et pour
        toujours apres), independamment de tout bug reel."""
        u = Utilisateur(
            nom="Jake", telephone="034", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT,
            niveau="L2", niveau_modifie_le=datetime(2026, 8, 15, 10, 0, 0),
        )
        with patch("app.referentiel_academique.datetime") as datetime_simule:
            datetime_simule.utcnow.return_value = datetime(2026, 8, 20, 0, 0, 0)
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


class TestConditionCerclesDisponibles(unittest.TestCase):
    """condition_cercles_disponibles() doit filtrer exactement les memes
    cercles que profil_correspond_au_cercle() accepterait un par un —
    seule la mecanique differe (condition SQL plutot que boucle Python)."""

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

            createur = Utilisateur(nom="Createur", telephone="0340000010", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT)
            session.add(createur); session.commit(); session.refresh(createur)
            self.createur_id = createur.id

            # Le paysage complet : un cercle libre, le cercle national qui
            # correspond a l'etudiant de test, et deux qui ne correspondent
            # pas (mauvais niveau, mauvaise filiere).
            session.add(CercleEtude(nom="Groupe libre", createur_id=self.createur_id))
            session.add(CercleEtude(
                nom="Finance L3", createur_id=self.createur_id,
                mention_id=self.mention_id, filiere_id=self.filiere_id, niveau="L3",
            ))
            session.add(CercleEtude(
                nom="Finance L2", createur_id=self.createur_id,
                mention_id=self.mention_id, filiere_id=self.filiere_id, niveau="L2",
            ))
            session.add(CercleEtude(
                nom="Droit L3", createur_id=self.createur_id,
                mention_id=autre_mention.id, filiere_id=self.autre_filiere_id, niveau="L3",
            ))
            session.commit()

    def _noms_disponibles(self, utilisateur) -> set:
        with Session(self.engine) as session:
            resultats = session.exec(
                select(CercleEtude).where(condition_cercles_disponibles(utilisateur, session))
            ).all()
            return {c.nom for c in resultats}

    def test_etudiant_avec_profil_complet_voit_le_libre_et_son_cercle_national(self):
        u = Utilisateur(nom="X", telephone="0340000011", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT,
                         filiere_id=self.filiere_id, niveau="L3")
        self.assertEqual(self._noms_disponibles(u), {"Groupe libre", "Finance L3"})

    def test_etudiant_ne_voit_pas_le_meme_cercle_national_a_un_autre_niveau(self):
        u = Utilisateur(nom="X", telephone="0340000012", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT,
                         filiere_id=self.filiere_id, niveau="L2")
        self.assertEqual(self._noms_disponibles(u), {"Groupe libre", "Finance L2"})

    def test_etudiant_ne_voit_pas_les_cercles_dune_autre_filiere(self):
        u = Utilisateur(nom="X", telephone="0340000013", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT,
                         filiere_id=self.filiere_id, niveau="L3")
        self.assertNotIn("Droit L3", self._noms_disponibles(u))

    def test_utilisateur_sans_profil_ne_voit_que_les_cercles_libres(self):
        u = Utilisateur(nom="X", telephone="0340000014", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT)
        self.assertEqual(self._noms_disponibles(u), {"Groupe libre"})

    def test_utilisateur_none_ne_voit_que_les_cercles_libres(self):
        self.assertEqual(self._noms_disponibles(None), {"Groupe libre"})

    def test_coherent_avec_profil_correspond_au_cercle_pour_chaque_cercle(self):
        """Verification croisee : pour un etudiant donne, l'ensemble
        renvoye par la condition SQL doit etre EXACTEMENT celui obtenu
        en filtrant chaque cercle un par un avec profil_correspond_au_cercle
        (plus l'appartenance a un cercle libre, deja couverte par les deux)."""
        u = Utilisateur(nom="X", telephone="0340000015", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT,
                         filiere_id=self.filiere_id, niveau="L3")
        with Session(self.engine) as session:
            tous = session.exec(select(CercleEtude)).all()
            attendu = {c.nom for c in tous if profil_correspond_au_cercle(u, c, session)}
        self.assertEqual(self._noms_disponibles(u), attendu)


if __name__ == "__main__":
    unittest.main()
