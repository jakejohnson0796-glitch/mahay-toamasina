"""
Verifie que peupler_donnees_initiales() (app/seed_data.py) reste
correct malgre les Faculte desormais creees par la migration
f2b8e6a1c9d3 (5 universites manquantes) sur une base neuve.

Bug reproduit ici (avant correctif) : l'ancienne garde d'idempotence
etait "if une Faculte quelconque existe, ne rien faire" — sur une base
neuve, les facultes des 5 autres universites (creees par la migration,
AVANT que ce module ne s'execute au demarrage) declenchaient cette
garde a tort, et Toamasina ne recevait jamais ses propres facultes/
filieres.

Lancer avec :
    python -m unittest tests.test_seed_data_avec_universites -v
"""
import unittest

from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

from app.models import Universite, Faculte, Filiere
from app.seed_data import peupler_donnees_initiales, STRUCTURE_UNIVERSITE


def _nouvel_engine_sqlite():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _activer_fk(connexion_dbapi, _record):
        connexion_dbapi.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine


class TestSeedDataAvecUniversites(unittest.TestCase):

    def setUp(self):
        self.engine = _nouvel_engine_sqlite()
        with Session(self.engine) as session:
            self.toamasina = Universite(nom="Universite de Toamasina", ville="Toamasina")
            session.add(self.toamasina); session.commit(); session.refresh(self.toamasina)
            self.toamasina_id = self.toamasina.id

            # Simule ce que fait la migration f2b8e6a1c9d3 : des Faculte
            # pour une AUTRE universite, creees AVANT que le seed ne
            # s'execute (meme ordre qu'au demarrage reel : migrations
            # puis seed_data.py).
            autre_universite = Universite(nom="Universite d'Antananarivo", ville="Antananarivo")
            session.add(autre_universite); session.commit(); session.refresh(autre_universite)
            session.add(Faculte(nom="Faculte des Sciences", universite_id=autre_universite.id))
            session.commit()

    def test_seed_toamasina_s_execute_malgre_facultes_d_une_autre_universite(self):
        with Session(self.engine) as session:
            peupler_donnees_initiales(session)

            facultes_toamasina = session.exec(
                select(Faculte).where(Faculte.universite_id == self.toamasina_id)
            ).all()
            self.assertEqual(len(facultes_toamasina), len(STRUCTURE_UNIVERSITE))

            nb_filieres_attendu = sum(len(f) for f in STRUCTURE_UNIVERSITE.values())
            filieres = session.exec(select(Filiere)).all()
            self.assertEqual(len(filieres), nb_filieres_attendu)

    def test_seed_reste_idempotent_appele_deux_fois(self):
        with Session(self.engine) as session:
            peupler_donnees_initiales(session)
            peupler_donnees_initiales(session)

            facultes_toamasina = session.exec(
                select(Faculte).where(Faculte.universite_id == self.toamasina_id)
            ).all()
            self.assertEqual(len(facultes_toamasina), len(STRUCTURE_UNIVERSITE), "Pas de doublon au 2e appel")

    def test_toutes_les_facultes_toamasina_ont_bien_universite_id(self):
        """NOT NULL depuis la migration e1a4c9d2b7f5 : une Faculte sans
        universite_id ferait planter l'insertion en base reelle."""
        with Session(self.engine) as session:
            peupler_donnees_initiales(session)
            for faculte in session.exec(select(Faculte)).all():
                self.assertIsNotNone(faculte.universite_id)


if __name__ == "__main__":
    unittest.main()
