"""
Reproduit le bug reel observe en production (log Render du 15/08) :
suppression d'un cercle 'Theme du jour — 08/08/2026' echouant avec
sqlalchemy.exc.IntegrityError (ForeignKeyViolation sur
themedujour_cercle_id_fkey), et verifie que le fix (detacher les lignes
ThemeDuJour avant de supprimer le cercle) resout le probleme sans perdre
l'historique des themes.

Lancer avec :
    python -m unittest tests.test_suppression_cercle -v
"""
import unittest
from datetime import date

from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine, select

from app.models import Utilisateur, CercleEtude, MembreCercle, ThemeDuJour, RoleUtilisateur


def _nouvel_engine_sqlite():
    """Un moteur SQLite en memoire avec les contraintes de cle etrangere
    activees (desactivees par defaut sur SQLite, contrairement a
    Postgres/Supabase utilise en production — sans ce PRAGMA, le test
    ne reproduirait pas le bug reel)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _activer_fk(connexion_dbapi, _record):
        connexion_dbapi.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine


class TestSuppressionCercleAvecThemeDuJour(unittest.TestCase):

    def setUp(self):
        self.engine = _nouvel_engine_sqlite()
        with Session(self.engine) as session:
            utilisateur = Utilisateur(
                nom="Jake", telephone="0340000000",
                mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT,
            )
            session.add(utilisateur)
            session.commit()
            session.refresh(utilisateur)
            self.utilisateur_id = utilisateur.id

            cercle = CercleEtude(nom="Theme du jour — 08/08/2026", createur_id=utilisateur.id)
            session.add(cercle)
            session.commit()
            session.refresh(cercle)
            self.cercle_id = cercle.id

            theme = ThemeDuJour(
                date_jour=date(2026, 8, 8), theme="Question test",
                amorce="Amorce test", cercle_id=cercle.id,
            )
            session.add(theme)
            session.commit()
            session.refresh(theme)
            self.theme_id = theme.id

    def test_le_bug_original_est_bien_reproductible(self):
        """Sans le fix (suppression 'brute' du cercle), on retombe
        exactement sur l'IntegrityError observee en production."""
        with self.assertRaises(IntegrityError):
            with Session(self.engine) as session:
                cercle = session.get(CercleEtude, self.cercle_id)
                session.delete(cercle)
                session.commit()

    def test_le_fix_supprime_le_cercle_sans_erreur(self):
        with Session(self.engine) as session:
            for theme_jour in session.exec(
                select(ThemeDuJour).where(ThemeDuJour.cercle_id == self.cercle_id)
            ).all():
                theme_jour.cercle_id = None
                session.add(theme_jour)
            cercle = session.get(CercleEtude, self.cercle_id)
            session.delete(cercle)
            session.commit()  # ne doit lever aucune exception

        with Session(self.engine) as session:
            self.assertIsNone(session.get(CercleEtude, self.cercle_id))

    def test_le_fix_conserve_l_historique_du_theme_du_jour(self):
        with Session(self.engine) as session:
            for theme_jour in session.exec(
                select(ThemeDuJour).where(ThemeDuJour.cercle_id == self.cercle_id)
            ).all():
                theme_jour.cercle_id = None
                session.add(theme_jour)
            session.delete(session.get(CercleEtude, self.cercle_id))
            session.commit()

        with Session(self.engine) as session:
            theme_recharge = session.get(ThemeDuJour, self.theme_id)
            self.assertIsNotNone(theme_recharge, "Le theme du jour ne doit pas etre supprime")
            self.assertEqual(theme_recharge.theme, "Question test")
            self.assertIsNone(theme_recharge.cercle_id, "Le lien vers le cercle supprime doit etre detache")


if __name__ == "__main__":
    unittest.main()
