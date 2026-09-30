"""Tests de la réconciliation canonique du référentiel Toamasina."""
import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

from app.models import (
    CercleEtude,
    Domaine,
    Faculte,
    Filiere,
    Mention,
    ProgrammeUniversitaire,
    RoleUtilisateur,
    Universite,
    Utilisateur,
    StatutCercle,
)
from app.referentiel_reconciliation import reconcilier


def nouvel_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def fk(connexion, _record):
        connexion.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine


def source_temporaire(formations):
    payload = {"formations": formations}
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(payload, f, ensure_ascii=False)
    f.close()
    return Path(f.name)


class TestSourceCanonique(unittest.TestCase):
    def test_source_ne_contient_ni_cca_ni_doublon_exact(self):
        path = Path(__file__).resolve().parents[1] / "mahay_toamasina_referentiel_source.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(
            [x for x in data["formations"] if (x.get("parcours") or "").strip().upper().startswith("CCA")]
        )
        cles = [
            (
                (x.get("composante") or "").strip().casefold(),
                (x.get("mention") or "").strip().casefold(),
                (x.get("niveau") or "").strip().casefold(),
                (x.get("type") or "").strip().casefold(),
                (x.get("parcours") or "").strip().casefold(),
            )
            for x in data["formations"]
        ]
        self.assertEqual(len(cles), len(set(cles)))


class TestReferentielReconciliation(unittest.TestCase):
    def test_fusionne_les_filieres_equivalentes_et_garde_une_offre(self):
        engine = nouvel_engine()
        path = source_temporaire([
            {
                "universite": "Université de Toamasina",
                "ville": "Toamasina",
                "composante": "Faculté DEG",
                "domaine": "Sciences de gestion",
                "mention": "Gestion",
                "niveau": "M1",
                "type": "Spécialisation",
                "parcours": "Commerce International",
                "statut": "Vérifié",
            }
        ])
        try:
            with Session(engine) as s:
                u = Universite(nom="Université de Toamasina")
                s.add(u); s.commit(); s.refresh(u)
                f = Faculte(
                    nom="Droit, Economie, Gestion, Mathematiques et Informatique (DEGMIA)",
                    universite_id=u.id,
                )
                s.add(f); s.commit(); s.refresh(f)
                d = Domaine(nom="Sciences de gestion")
                s.add(d); s.commit(); s.refresh(d)
                m = Mention(nom="Gestion", domaine_id=d.id)
                s.add(m); s.commit(); s.refresh(m)
                f1 = Filiere(
                    nom="Commerce International", faculte_id=f.id,
                    mention_id=m.id, niveau="M1",
                )
                f2 = Filiere(
                    nom="Commerce International ", faculte_id=f.id,
                    mention_id=m.id, niveau="M1",
                )
                s.add(f1); s.add(f2); s.commit(); s.refresh(f1); s.refresh(f2)
                s.add(ProgrammeUniversitaire(
                    universite_id=u.id, filiere_id=f1.id, est_active=True,
                ))
                s.add(ProgrammeUniversitaire(
                    universite_id=u.id, filiere_id=f2.id, est_active=True,
                ))
                s.commit()

                reconcilier(s, str(path))

                filieres = s.exec(
                    select(Filiere).where(
                        Filiere.faculte_id == f.id,
                        Filiere.mention_id == m.id,
                        Filiere.niveau == "M1",
                    )
                ).all()
                self.assertEqual(len(filieres), 1)
                offres = s.exec(
                    select(ProgrammeUniversitaire).where(
                        ProgrammeUniversitaire.universite_id == u.id,
                        ProgrammeUniversitaire.est_active == True,  # noqa: E712
                    )
                ).all()
                self.assertEqual(len(offres), 1)
                self.assertEqual(offres[0].filiere_id, filieres[0].id)
        finally:
            path.unlink(missing_ok=True)

    def test_desactive_une_ancienne_offre_absente_de_la_source(self):
        engine = nouvel_engine()
        path = source_temporaire([
            {
                "universite": "Université de Toamasina",
                "ville": "Toamasina",
                "composante": "Faculté DEG",
                "domaine": "Sciences de gestion",
                "mention": "Gestion",
                "niveau": "M1",
                "type": "Spécialisation",
                "parcours": "Commerce International",
                "statut": "Vérifié",
            }
        ])
        try:
            with Session(engine) as s:
                u = Universite(nom="Université de Toamasina")
                f = Faculte(nom="DEGMIA", universite_id=1)
                s.add(u); s.commit(); s.refresh(u)
                f.universite_id = u.id
                s.add(f); s.commit(); s.refresh(f)
                m = Mention(nom="Gestion")
                stale_m = Mention(nom="Gestion Ancienne")
                s.add(m); s.add(stale_m); s.commit(); s.refresh(m); s.refresh(stale_m)
                wanted = Filiere(nom="Commerce International", faculte_id=f.id, mention_id=m.id, niveau="M1")
                stale = Filiere(nom="Ancien parcours", faculte_id=f.id, mention_id=stale_m.id, niveau="M1")
                s.add(wanted); s.add(stale); s.commit(); s.refresh(wanted); s.refresh(stale)
                old_program = ProgrammeUniversitaire(
                    universite_id=u.id, filiere_id=stale.id, est_active=True,
                )
                s.add(old_program); s.commit(); s.refresh(old_program)

                reconcilier(s, str(path))

                old_program = s.get(ProgrammeUniversitaire, old_program.id)
                self.assertFalse(old_program.est_active)
        finally:
            path.unlink(missing_ok=True)

    def test_tronc_commun_ne_publie_pas_un_parcours_technique(self):
        engine = nouvel_engine()
        path = source_temporaire([
            {
                "universite": "Université de Toamasina",
                "ville": "Toamasina",
                "composante": "Faculté DEG",
                "domaine": "Sciences de gestion",
                "mention": "Gestion",
                "niveau": "L1",
                "type": "Tronc commun",
                "parcours": "Tronc commun",
                "statut": "Vérifié",
            }
        ])
        try:
            with Session(engine) as s:
                u = Universite(nom="Université de Toamasina")
                s.add(u); s.commit(); s.refresh(u)
                f = Faculte(nom="DEGMIA", universite_id=u.id)
                m = Mention(nom="Gestion")
                s.add(f); s.add(m); s.commit(); s.refresh(f); s.refresh(m)
                legacy = Filiere(
                    nom="Tronc commun", faculte_id=f.id,
                    mention_id=m.id, niveau="L1",
                )
                s.add(legacy); s.commit(); s.refresh(legacy)
                program = ProgrammeUniversitaire(
                    universite_id=u.id, filiere_id=legacy.id, est_active=True,
                )
                s.add(program); s.commit(); s.refresh(program)

                rapport = reconcilier(s, str(path))

                program = s.get(ProgrammeUniversitaire, program.id)
                self.assertFalse(program.est_active)

                technique = s.exec(
                    select(Filiere).where(
                        Filiere.mention_id == m.id,
                        Filiere.faculte_id == f.id,
                        Filiere.niveau == "L1",
                        Filiere.nom == "Tronc commun",
                    )
                ).one()
                offre_technique = s.exec(
                    select(ProgrammeUniversitaire).where(
                        ProgrammeUniversitaire.universite_id == u.id,
                        ProgrammeUniversitaire.filiere_id == technique.id,
                        ProgrammeUniversitaire.est_active == True,  # noqa: E712
                    )
                ).first()
                self.assertIsNotNone(offre_technique)
                self.assertIn((m.id, "L1"), rapport.tronc_commun)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
