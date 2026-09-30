"""Regression sur le basculement des anciens parcours Tronc commun."""
import json
import tempfile
import unittest
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Faculte, Filiere, Mention, ProgrammeUniversitaire, Universite
from scripts import import_academic_data


class TestImportStrictToamasina(unittest.TestCase):
    def test_un_ancien_parcours_marque_tronc_commun_est_desactive(self):
        moteur = create_engine("sqlite://", connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(moteur)

        with Session(moteur) as session:
            universite = Universite(nom="Université de Toamasina")
            session.add(universite)
            session.commit()
            session.refresh(universite)

            faculte = Faculte(
                nom="Droit, Economie, Gestion, Mathematiques et Informatique (DEGMIA)",
                universite_id=universite.id,
            )
            mention = Mention(nom="Droit et Sciences politiques")
            session.add_all([faculte, mention])
            session.commit()
            session.refresh(faculte)
            session.refresh(mention)

            filiere = Filiere(
                nom="Droit général",
                faculte_id=faculte.id,
                mention_id=mention.id,
                niveau="L1",
            )
            session.add(filiere)
            session.commit()
            session.refresh(filiere)

            offre = ProgrammeUniversitaire(
                universite_id=universite.id,
                filiere_id=filiere.id,
                est_active=True,
            )
            session.add(offre)
            session.commit()

        source = Path(tempfile.mkstemp(suffix=".json")[1])
        try:
            source.write_text(
                json.dumps(
                    {
                        "formations": [
                            {
                                "universite": "Université de Toamasina",
                                "ville": "Toamasina",
                                "composante": "Faculté DEG",
                                "domaine": "Droit et sciences politiques",
                                "mention": "Droit et Sciences politiques",
                                "niveau": "L1",
                                "type": "Tronc commun",
                                "parcours": "Droit général",
                                "debut_specialisation": None,
                                "fin_specialisation": None,
                                "statut": "Vérifié",
                                "source": "test",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            ancien_moteur = import_academic_data.engine
            import_academic_data.engine = moteur
            try:
                import_academic_data.importer(str(source))
            finally:
                import_academic_data.engine = ancien_moteur

            with Session(moteur) as session:
                offre_rechargee = session.exec(select(ProgrammeUniversitaire)).one()
                self.assertFalse(offre_rechargee.est_active)
        finally:
            source.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
