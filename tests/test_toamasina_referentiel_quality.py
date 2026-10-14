"""Contrôles qualité du référentiel canonique de Toamasina.

Ces tests protègent les sélecteurs étudiants contre les doublons, les
niveaux oubliés et les formations sans preuve suffisamment précise.
"""
import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

from app.models import Domaine, Faculte, Filiere, Mention, ProgrammeUniversitaire, Universite
from app.referentiel_reconciliation import reconcilier


def nouvel_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def activer_cles_etrangeres(connexion, _record):
        connexion.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine


def source_temporaire(formations):
    fichier = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump({"formations": formations}, fichier, ensure_ascii=False)
    fichier.close()
    return Path(fichier.name)


RACINE = Path(__file__).resolve().parents[1]
SOURCE = RACINE / "mahay_toamasina_referentiel_source.json"


class TestQualiteSourceToamasina(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.formations = self.data["formations"]

    def test_droit_l1_l2_gardent_le_parcours_nomme_sous_type_tronc_commun(self):
        lignes = [
            ligne for ligne in self.formations
            if ligne["composante"] == "Faculté DEG"
            and ligne["mention"] == "Droit et Sciences politiques"
            and ligne["niveau"] in {"L1", "L2"}
        ]
        self.assertEqual({ligne["niveau"] for ligne in lignes}, {"L1", "L2"})
        self.assertTrue(all(ligne["type"] == "Tronc commun" for ligne in lignes))
        self.assertTrue(all(ligne["parcours"] == "Droit général" for ligne in lignes))

    def test_gestion_commerce_international_est_present_en_m1_et_m2(self):
        niveaux = {
            ligne["niveau"]
            for ligne in self.formations
            if ligne["composante"] == "Faculté DEG"
            and ligne["mention"] == "Gestion"
            and ligne["parcours"] == "Commerce International"
        }
        self.assertEqual(niveaux, {"M1", "M2"})

    def test_domaines_flsh_sont_harmonises(self):
        flsh = [
            ligne for ligne in self.formations
            if ligne["composante"] == "Faculté des Lettres et Sciences Humaines"
        ]
        self.assertTrue(flsh)
        self.assertEqual(
            {ligne["domaine"] for ligne in flsh},
            {"Arts, Lettres et Sciences Humaines"},
        )

    def test_lignes_publiees_sont_sourcees_et_sans_doublon(self):
        clefs = []
        for ligne in self.formations:
            for champ in ("universite", "ville", "composante", "domaine", "mention", "niveau", "type", "parcours", "statut", "source"):
                self.assertTrue(str(ligne.get(champ) or "").strip(), f"Champ manquant {champ}: {ligne}")
            self.assertIn(ligne["statut"].strip().casefold(), {"vérifié", "confirmé"})
            self.assertTrue(ligne["source"].startswith("https://"))
            clefs.append(tuple(
                str(ligne.get(champ) or "").strip().casefold()
                for champ in ("universite", "composante", "mention", "niveau", "type", "parcours")
            ))
        self.assertEqual(len(clefs), len(set(clefs)), "La source contient des lignes académiques dupliquées.")

    def test_cca_m2_est_publie_et_m1_reste_en_attente_de_confirmation(self):
        publiees = [
            ligne for ligne in self.formations
            if "cca" in str(ligne.get("parcours") or "").casefold()
        ]
        self.assertEqual(len(publiees), 1)
        self.assertEqual(publiees[0]["niveau"], "M2")
        self.assertEqual(publiees[0]["statut"], "Confirmé")
        self.assertIn("scribd.com/document/689634398", publiees[0]["source"])
        en_attente = self.data.get("audit_referentiel", {}).get("formations_a_verifier_avant_publication", [])
        cca = [item for item in en_attente if "cca" in str(item).casefold()]
        self.assertEqual(len(cca), 1)
        self.assertEqual(cca[0]["niveaux"], ["M1"])
        self.assertIn("À vérifier", cca[0]["statut"])

    def test_issedd_est_publie_sur_les_niveaux_licence_et_master(self):
        lignes = [
            ligne for ligne in self.formations
            if ligne["composante"] == "Institut Supérieur des Sciences, Environnement et Développement Durable (ISSEDD-GRENE)"
            and ligne["mention"] == "Sciences de l’Environnement et du Développement"
        ]
        self.assertEqual({ligne["niveau"] for ligne in lignes}, {"L1", "L2", "L3", "M1", "M2"})
        self.assertTrue(all(ligne["statut"] == "Confirmé" for ligne in lignes))
        self.assertTrue(all("mesupres.gov.mg" in ligne["source"] for ligne in lignes))

    def test_itpt_expose_les_parcours_officiels_de_tourisme_et_patrimoine(self):
        composante = "Institut du Tourisme, des Patrimoines et des Territoires (ITPT)"
        attendus = {
            "Valorisation du Tourisme, des Patrimoines et des Territoires",
            "Tourisme et Patrimoine dans les Tropicaux",
            "Socio management et Développement Local",
        }
        lignes = [ligne for ligne in self.formations if ligne["composante"] == composante]
        self.assertEqual({ligne["niveau"] for ligne in lignes}, {"L1", "L2", "L3"})
        self.assertEqual({ligne["parcours"] for ligne in lignes}, attendus)
        self.assertEqual(len(lignes), 9)
        self.assertTrue(all(ligne["mention"] == "Valorisation du Tourisme, des Patrimoines et des Territoires" for ligne in lignes))
        self.assertTrue(all(ligne["statut"] == "Confirmé" for ligne in lignes))

    def test_niveaux_l1_et_l2_sont_presents_pour_mia_et_physique_chimie(self):
        attendus = {
            ("Faculté des Sciences et Technologie", "Mathématiques, Informatique et Applications"): {"L1", "L2"},
            ("Faculté des Sciences et Technologie", "Physique-Chimie"): {"L1"},
        }
        for (composante, mention), niveaux_attendus in attendus.items():
            niveaux = {
                ligne["niveau"] for ligne in self.formations
                if ligne["composante"] == composante
                and ligne["mention"] == mention
                and ligne["type"].strip().casefold() == "tronc commun"
            }
            self.assertTrue(niveaux_attendus.issubset(niveaux), f"Niveaux manquants pour {mention}: {niveaux_attendus - niveaux}")

    def test_perimetre_elargi_est_documente_sans_publier_des_niveaux_devines(self):
        a_verifier = self.data.get("audit_referentiel", {}).get("formations_a_verifier_avant_publication", [])
        composants = {str(ligne.get("composante") or "") for ligne in a_verifier}
        self.assertIn("Faculté de Médecine", composants)
        self.assertIn("École Supérieure Polytechnique de Toamasina (ESPT)", composants)
        self.assertTrue(all("À vérifier" in str(ligne.get("statut") or "") for ligne in a_verifier))


class TestCorrectionDomainesHistoriques(unittest.TestCase):
    def test_domaine_historique_flsh_est_corrige_selon_la_source(self):
        engine = nouvel_engine()
        path = source_temporaire([
            {
                "universite": "Université de Toamasina",
                "ville": "Toamasina",
                "composante": "Faculté des Lettres et Sciences Humaines",
                "domaine": "Arts, Lettres et Sciences Humaines",
                "mention": "Philosophie",
                "niveau": "L1",
                "type": "Parcours",
                "parcours": "Philosophie",
                "statut": "Confirmé",
            }
        ])
        try:
            with Session(engine) as session:
                universite = Universite(nom="Université de Toamasina")
                ancien_domaine = Domaine(nom="Lettres et sciences humaines")
                domaine_canonique = Domaine(nom="Arts, Lettres et Sciences Humaines")
                session.add(universite)
                session.add(ancien_domaine)
                session.add(domaine_canonique)
                session.commit()
                session.refresh(universite)
                session.refresh(ancien_domaine)
                session.refresh(domaine_canonique)
                mention = Mention(nom="Philosophie", domaine_id=ancien_domaine.id)
                session.add(mention)
                session.commit()
                session.refresh(mention)

                reconcilier(session, str(path))

                mention = session.exec(
                    select(Mention).where(Mention.nom == "Philosophie")
                ).one()
                self.assertEqual(mention.domaine_id, domaine_canonique.id)
                self.assertEqual(mention.domaine.nom, "Arts, Lettres et Sciences Humaines")
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
