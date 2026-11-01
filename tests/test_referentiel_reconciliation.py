"""Tests de la réconciliation canonique du référentiel Toamasina."""
import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

from app.models import (
    CercleEtude,
    Document,
    DemandeChangementFiliere,
    DemandeCreationCercle,
    Domaine,
    Faculte,
    Filiere,
    Mention,
    ProgrammeUniversitaire,
    RoleUtilisateur,
    Universite,
    Utilisateur,
    StatutCercle,
    TypeDocument,
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
    def test_source_garde_cca_m1_et_m2_en_attente_sans_preuve_officielle(self):
        path = Path(__file__).resolve().parents[1] / "mahay_toamasina_referentiel_source.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        cca = [x for x in data["formations"] if "cca" in (x.get("parcours") or "").casefold()]
        self.assertEqual(len(cca), 1)
        self.assertEqual(cca[0]["niveau"], "M2")
        self.assertEqual(cca[0]["statut"], "À vérifier")
        audit_cca = [
            x for x in data["audit_referentiel"]["formations_a_verifier_avant_publication"]
            if "cca" in json.dumps(x, ensure_ascii=False).casefold()
        ]
        self.assertEqual(len(audit_cca), 1)
        self.assertEqual(audit_cca[0]["niveaux"], ["M1", "M2"])
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

    def test_type_tronc_commun_ne_remplace_pas_un_parcours_nomme(self):
        engine = nouvel_engine()
        path = source_temporaire([
            {
                "universite": "Université de Toamasina",
                "ville": "Toamasina",
                "composante": "Faculté DEG",
                "domaine": "Droit et sciences politiques",
                "mention": "Droit et Sciences politiques",
                "niveau": "L1",
                "type": "Tronc commun",
                "parcours": "Droit général",
                "statut": "Vérifié",
            }
        ])
        try:
            with Session(engine) as s:
                u = Universite(nom="Université de Toamasina")
                s.add(u); s.commit(); s.refresh(u)
                f = Faculte(nom="DEGMIA", universite_id=u.id)
                d = Domaine(nom="Droit et sciences politiques")
                s.add(f); s.add(d); s.commit(); s.refresh(f); s.refresh(d)
                m = Mention(nom="Droit et Sciences politiques", domaine_id=d.id)
                s.add(m); s.commit(); s.refresh(m)

                droit_general = Filiere(
                    nom="Droit général", faculte_id=f.id, mention_id=m.id, niveau="L1"
                )
                pseudo_tronc = Filiere(
                    nom="Tronc commun", faculte_id=f.id, mention_id=m.id, niveau="L1"
                )
                s.add(droit_general); s.add(pseudo_tronc); s.commit()
                s.refresh(droit_general); s.refresh(pseudo_tronc)
                offre_droit = ProgrammeUniversitaire(
                    universite_id=u.id, filiere_id=droit_general.id, est_active=False
                )
                offre_tronc = ProgrammeUniversitaire(
                    universite_id=u.id, filiere_id=pseudo_tronc.id, est_active=True
                )
                s.add(offre_droit); s.add(offre_tronc); s.commit()
                s.refresh(offre_droit); s.refresh(offre_tronc)

                rapport = reconcilier(s, str(path))

                offre_droit = s.get(ProgrammeUniversitaire, offre_droit.id)
                offre_tronc = s.get(ProgrammeUniversitaire, offre_tronc.id)
                self.assertTrue(offre_droit.est_active)
                self.assertFalse(offre_tronc.est_active)
                self.assertIn((m.id, "L1"), rapport.tronc_commun)
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
                self.assertTrue(program.est_active)

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


    def test_fusionne_mentions_normalisees_meme_si_le_nom_canonique_existe(self):
        engine = nouvel_engine()
        nom_canonique = "Enseignement-Apprentissage et didactique d’Histoire-Géographie"
        nom_ancien = "Enseignement-Apprentissage et didactique d'Histoire-Geographie"
        parcours_canonique = "Enseignement - Apprentissage et didactique d’Histoire-Géographie"
        parcours_ancien = "Enseignement - Apprentissage et didactique d'Histoire-Geographie"
        path = source_temporaire([
            {
                "universite": "Université de Toamasina",
                "ville": "Toamasina",
                "composante": "École Normale Supérieure",
                "domaine": "Sciences de l’éducation",
                "mention": nom_canonique,
                "niveau": "M1",
                "type": "Spécialisation",
                "parcours": parcours_canonique,
                "statut": "Vérifié",
            }
        ])
        try:
            with Session(engine) as s:
                universite = Universite(nom="Université de Toamasina", ville="Toamasina")
                s.add(universite); s.commit(); s.refresh(universite)
                faculte = Faculte(nom="École Normale Supérieure", universite_id=universite.id)
                domaine = Domaine(nom="Sciences de l’éducation")
                s.add(faculte); s.add(domaine); s.commit()
                s.refresh(faculte); s.refresh(domaine)

                canonique = Mention(nom=nom_canonique, domaine_id=domaine.id)
                ancien = Mention(nom=nom_ancien, domaine_id=domaine.id)
                s.add(canonique); s.add(ancien); s.commit()
                s.refresh(canonique); s.refresh(ancien)

                filiere_canonique = Filiere(
                    nom=parcours_canonique, faculte_id=faculte.id,
                    mention_id=canonique.id, niveau="M1",
                )
                filiere_ancienne = Filiere(
                    nom=parcours_ancien, faculte_id=faculte.id,
                    mention_id=ancien.id, niveau="M1",
                )
                s.add(filiere_canonique); s.add(filiere_ancienne); s.commit()
                s.refresh(filiere_canonique); s.refresh(filiere_ancienne)
                s.add(ProgrammeUniversitaire(
                    universite_id=universite.id, filiere_id=filiere_canonique.id,
                    annee_academique="2025-2026", est_active=True,
                ))
                # Même année : doublon à consolider.
                s.add(ProgrammeUniversitaire(
                    universite_id=universite.id, filiere_id=filiere_ancienne.id,
                    annee_academique="2025-2026", est_active=False,
                ))
                # Année distincte : conserver l'archive, sans laisser deux offres actives.
                s.add(ProgrammeUniversitaire(
                    universite_id=universite.id, filiere_id=filiere_ancienne.id,
                    annee_academique="2024-2025", est_active=True,
                ))

                utilisateur = Utilisateur(
                    nom="Etudiant test",
                    mot_de_passe_hash="hash-test",
                    role=RoleUtilisateur.ETUDIANT,
                    universite_id=universite.id,
                    faculte_id=faculte.id,
                    mention_id=ancien.id,
                    filiere_id=filiere_ancienne.id,
                    niveau="M1",
                )
                s.add(utilisateur); s.commit(); s.refresh(utilisateur)

                cercle = CercleEtude(
                    nom="Cercle test",
                    mention_id=ancien.id,
                    filiere_id=filiere_ancienne.id,
                    niveau="M1",
                    createur_id=utilisateur.id,
                    statut=StatutCercle.ACTIF,
                )
                demande_cercle = DemandeCreationCercle(
                    utilisateur_id=utilisateur.id,
                    mention_id=ancien.id,
                    filiere_id=filiere_ancienne.id,
                    niveau="M1",
                    nom="Demande cercle test",
                    raison="Test de fusion de mention",
                )
                # Les deux colonnes de parcours peuvent référencer l'ancienne filière.
                # Le test vérifie que la réconciliation ne laisse aucune FK orpheline.
                demande_changement = DemandeChangementFiliere(
                    utilisateur_id=utilisateur.id,
                    ancienne_filiere_id=filiere_ancienne.id,
                    nouvelle_mention_id=ancien.id,
                    nouvelle_filiere_id=filiere_ancienne.id,
                    motif="Test de fusion de mention",
                )
                document = Document(
                    reference="TEST-ENS-DOC-001",
                    titre="Cours de didactique — test de réconciliation",
                    matiere="Didactique",
                    type_document=TypeDocument.COURS,
                    annee=2026,
                    filiere_id=filiere_ancienne.id,
                    uploader_id=utilisateur.id,
                    chemin_fichier="tests/fixtures/cours-ens-test.pdf",
                )
                s.add(cercle); s.add(demande_cercle); s.add(demande_changement); s.add(document); s.commit()
                s.refresh(cercle); s.refresh(demande_cercle); s.refresh(demande_changement); s.refresh(document)

                # La simulation doit détecter la fusion sans conserver aucune écriture.
                rapport_dry = reconcilier(s, str(path), dry_run=True)
                self.assertGreaterEqual(rapport_dry.filieres_fusionnees, 1)
                s.expire_all()
                self.assertIsNotNone(s.get(Mention, ancien.id))
                self.assertEqual(s.get(Utilisateur, utilisateur.id).mention_id, ancien.id)

                reconcilier(s, str(path))
                s.expire_all()

                self.assertIsNone(s.get(Mention, ancien.id))
                mentions = s.exec(
                    select(Mention).where(Mention.nom == nom_canonique)
                ).all()
                self.assertEqual(len(mentions), 1)
                filieres = s.exec(
                    select(Filiere).where(
                        Filiere.faculte_id == faculte.id,
                        Filiere.mention_id == canonique.id,
                        Filiere.niveau == "M1",
                    )
                ).all()
                self.assertEqual(len(filieres), 1)
                filiere_id = filieres[0].id

                offres = s.exec(
                    select(ProgrammeUniversitaire).where(
                        ProgrammeUniversitaire.universite_id == universite.id,
                        ProgrammeUniversitaire.filiere_id == filiere_id,
                    )
                ).all()
                self.assertEqual(len(offres), 2)
                offres_par_annee = {offre.annee_academique: offre for offre in offres}
                self.assertTrue(offres_par_annee["2025-2026"].est_active)
                self.assertFalse(offres_par_annee["2024-2025"].est_active)

                utilisateur_final = s.get(Utilisateur, utilisateur.id)
                cercle_final = s.get(CercleEtude, cercle.id)
                demande_cercle_finale = s.get(DemandeCreationCercle, demande_cercle.id)
                demande_changement_finale = s.get(DemandeChangementFiliere, demande_changement.id)
                self.assertEqual(utilisateur_final.mention_id, canonique.id)
                self.assertEqual(utilisateur_final.filiere_id, filiere_id)
                self.assertEqual(cercle_final.mention_id, canonique.id)
                self.assertEqual(cercle_final.filiere_id, filiere_id)
                self.assertEqual(demande_cercle_finale.mention_id, canonique.id)
                self.assertEqual(demande_cercle_finale.filiere_id, filiere_id)
                self.assertEqual(demande_changement_finale.nouvelle_mention_id, canonique.id)
                self.assertEqual(demande_changement_finale.ancienne_filiere_id, filiere_id)
                self.assertEqual(demande_changement_finale.nouvelle_filiere_id, filiere_id)
                document_final = s.get(Document, document.id)
                self.assertEqual(document_final.filiere_id, filiere_id)
        finally:
            path.unlink(missing_ok=True)

    def test_dry_run_annule_aussi_les_ecritures_intermediaires(self):
        engine = nouvel_engine()
        path = source_temporaire([
            {
                "universite": "Université de Toamasina",
                "ville": "Toamasina",
                "composante": "Faculté DEG",
                "domaine": "Domaine temporaire de test",
                "mention": "Mention temporaire de test",
                "niveau": "L1",
                "type": "Spécialisation",
                "parcours": "Parcours temporaire de test",
                "statut": "Vérifié",
            }
        ])
        try:
            with Session(engine) as s:
                universite = Universite(nom="Université de Toamasina")
                s.add(universite)
                s.commit()
                s.refresh(universite)

                rapport = reconcilier(s, str(path), dry_run=True)

                self.assertEqual(rapport.offres_activees, 1)
                self.assertEqual(s.exec(select(Faculte)).all(), [])
                self.assertEqual(s.exec(select(Domaine)).all(), [])
                self.assertEqual(s.exec(select(Mention)).all(), [])
                self.assertEqual(s.exec(select(Filiere)).all(), [])
                self.assertEqual(s.exec(select(ProgrammeUniversitaire)).all(), [])
        finally:
            path.unlink(missing_ok=True)



if __name__ == "__main__":
    unittest.main()
