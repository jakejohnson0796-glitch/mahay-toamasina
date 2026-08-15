"""
Verifie la contrainte anti-doublon des cercles nationaux (index
ix_cercle_national_unique_actif, migration e1a4c9d2b7f5) :
- deux cercles ACTIFS avec exactement la meme (mention_id, filiere_id,
  niveau) sont interdits par la base ;
- les cercles "libres" (au moins un des 3 champs = NULL) restent
  illimites, comme avant cette evolution.

Lancer avec :
    python -m unittest tests.test_contrainte_cercle_national -v
"""
import unittest

from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine

from app.models import Universite, Mention, Filiere, Faculte, CercleEtude, Utilisateur, RoleUtilisateur


def _nouvel_engine_sqlite():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _activer_fk(connexion_dbapi, _record):
        connexion_dbapi.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine


class TestContrainteCercleNational(unittest.TestCase):

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

            utilisateur = Utilisateur(nom="Jake", telephone="0340001111", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT)
            session.add(utilisateur); session.commit(); session.refresh(utilisateur)
            self.utilisateur_id = utilisateur.id

    def test_deux_cercles_identiques_mention_filiere_niveau_sont_rejetes(self):
        with Session(self.engine) as session:
            session.add(CercleEtude(
                nom="Finance L3 A", createur_id=self.utilisateur_id,
                mention_id=self.mention_id, filiere_id=self.filiere_id, niveau="L3",
            ))
            session.commit()

        with Session(self.engine) as session:
            session.add(CercleEtude(
                nom="Finance L3 B (doublon)", createur_id=self.utilisateur_id,
                mention_id=self.mention_id, filiere_id=self.filiere_id, niveau="L3",
            ))
            with self.assertRaises(IntegrityError):
                session.commit()

    def test_meme_filiere_niveau_different_est_autorise(self):
        with Session(self.engine) as session:
            session.add(CercleEtude(
                nom="Finance L3", createur_id=self.utilisateur_id,
                mention_id=self.mention_id, filiere_id=self.filiere_id, niveau="L3",
            ))
            session.add(CercleEtude(
                nom="Finance L2", createur_id=self.utilisateur_id,
                mention_id=self.mention_id, filiere_id=self.filiere_id, niveau="L2",
            ))
            session.commit()  # ne doit pas lever

    def test_cercles_libres_sans_niveau_illimites(self):
        with Session(self.engine) as session:
            for i in range(3):
                session.add(CercleEtude(nom=f"Groupe libre {i}", createur_id=self.utilisateur_id))
            session.commit()  # ne doit pas lever, meme sans mention/filiere/niveau

    def test_cercle_avec_mention_seule_sans_niveau_illimite(self):
        """Tant qu'un des 3 champs est NULL, la contrainte ne s'applique
        pas — seuls les cercles COMPLETS (les 3 renseignes) sont
        concernes par l'unicite."""
        with Session(self.engine) as session:
            session.add(CercleEtude(
                nom="A", createur_id=self.utilisateur_id,
                mention_id=self.mention_id, filiere_id=self.filiere_id,  # niveau manquant
            ))
            session.add(CercleEtude(
                nom="B", createur_id=self.utilisateur_id,
                mention_id=self.mention_id, filiere_id=self.filiere_id,  # niveau manquant aussi
            ))
            session.commit()  # ne doit pas lever


if __name__ == "__main__":
    unittest.main()
