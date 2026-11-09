"""Parcours de gestion des cours, devoirs, notes et correction assistée."""

import json
import os
import re
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from pathlib import Path

_DB_FICHIER = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FICHIER}"
os.environ.setdefault("SESSION_SECRET_KEY", "cle-test-classe-virtuelle-jamais-en-production")

from jinja2 import Environment, FileSystemLoader  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel, Session, select  # noqa: E402

from app.main import app  # noqa: E402
from app import rate_limit  # noqa: E402
from app.database import engine  # noqa: E402
from app.auth import hacher_mot_de_passe  # noqa: E402
from app.models import (  # noqa: E402
    Utilisateur,
    RoleUtilisateur,
    Cours,
    InscriptionCours,
    Devoir,
    RenduDevoir,
)


ROOT = Path(__file__).resolve().parents[1]
MOT_DE_PASSE = "MotDePasse123!"


def _connecter(client, telephone):
    page = client.get("/connexion")
    jeton = re.search(r'name="_csrf" value="([^"]+)"', page.text).group(1)
    reponse = client.post(
        "/connexion",
        data={"telephone": telephone, "mot_de_passe": MOT_DE_PASSE, "_csrf": jeton},
        follow_redirects=False,
    )
    assert reponse.status_code in (302, 303), reponse.text
    return jeton


class TestClasseDevoirs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SQLModel.metadata.create_all(engine)

    def setUp(self):
        rate_limit._tentatives.clear()
        with Session(engine) as session:
            for table in (RenduDevoir, Devoir, InscriptionCours, Cours, Utilisateur):
                for ligne in session.exec(select(table)).all():
                    session.delete(ligne)
            session.commit()

            prof = Utilisateur(
                nom="Professeur principal",
                telephone="0341101001",
                mot_de_passe_hash=hacher_mot_de_passe(MOT_DE_PASSE),
                role=RoleUtilisateur.PROFESSEUR,
            )
            autre_prof = Utilisateur(
                nom="Autre professeur",
                telephone="0341101002",
                mot_de_passe_hash=hacher_mot_de_passe(MOT_DE_PASSE),
                role=RoleUtilisateur.PROFESSEUR,
            )
            etudiant = Utilisateur(
                nom="Etudiant inscrit",
                telephone="0341101003",
                mot_de_passe_hash=hacher_mot_de_passe(MOT_DE_PASSE),
                role=RoleUtilisateur.ETUDIANT,
            )
            session.add_all([prof, autre_prof, etudiant])
            session.commit()
            for user in (prof, autre_prof, etudiant):
                session.refresh(user)
            self.prof_id = prof.id
            self.autre_prof_id = autre_prof.id
            self.etudiant_id = etudiant.id

            cours = Cours(
                nom="Comptabilité générale",
                matiere="Comptabilité",
                niveau="L2",
                description="Cours de comptabilité.",
                objectifs="Savoir enregistrer les opérations.",
                professeur_id=prof.id,
                code_invitation="ABCD2345",
            )
            session.add(cours)
            session.commit()
            session.refresh(cours)
            self.cours_id = cours.id

            session.add(InscriptionCours(cours_id=cours.id, utilisateur_id=etudiant.id))
            devoir = Devoir(
                cours_id=cours.id,
                titre="Bilan comptable",
                description="Établir le bilan et expliquer les postes.",
                bareme=30.0,
                criteres_json=json.dumps([
                    {"nom": "Exactitude", "points": 15.0},
                    {"nom": "Méthode", "points": 10.0},
                    {"nom": "Présentation", "points": 5.0},
                ]),
            )
            session.add(devoir)
            session.commit()
            session.refresh(devoir)
            self.devoir_id = devoir.id

    def _csrf(self, client):
        page = client.get("/connexion")
        return re.search(r'name="_csrf" value="([^"]+)"', page.text).group(1)

    def test_creation_cours_code_invitation_et_objectifs(self):
        client = TestClient(app)
        jeton = _connecter(client, "0341101001")
        reponse = client.post(
            "/classe/creer",
            data={
                "_csrf": jeton,
                "nom": "Analyse financière",
                "matiere": "Finance",
                "niveau": "L3",
                "description": "Étude des états financiers.",
                "objectifs": "Interpréter les ratios et argumenter un diagnostic.",
            },
            follow_redirects=False,
        )
        self.assertEqual(reponse.status_code, 303)
        with Session(engine) as session:
            cours = session.exec(
                select(Cours).where(Cours.nom == "Analyse financière")
            ).first()
        self.assertIsNotNone(cours)
        self.assertEqual(cours.objectifs, "Interpréter les ratios et argumenter un diagnostic.")
        self.assertRegex(cours.code_invitation or "", r"^[A-Z2-9]{8}$")

    def test_code_invitation_inscrit_un_etudiant_et_est_scoped(self):
        with Session(engine) as session:
            inscription = session.exec(
                select(InscriptionCours).where(
                    InscriptionCours.cours_id == self.cours_id,
                    InscriptionCours.utilisateur_id == self.etudiant_id,
                )
            ).first()
            if inscription:
                session.delete(inscription)
                session.commit()
        client = TestClient(app)
        jeton = _connecter(client, "0341101003")
        reponse = client.post(
            "/classe/rejoindre",
            data={"_csrf": jeton, "code": " abcd2345 "},
            follow_redirects=False,
        )
        self.assertEqual(reponse.status_code, 303)
        self.assertIn(f"/classe/{self.cours_id}", reponse.headers["location"])
        with Session(engine) as session:
            inscriptions = session.exec(
                select(InscriptionCours).where(
                    InscriptionCours.cours_id == self.cours_id,
                    InscriptionCours.utilisateur_id == self.etudiant_id,
                )
            ).all()
        self.assertEqual(len(inscriptions), 1)

    def test_seul_le_professeur_proprietaire_peut_modifier_le_cours(self):
        client_autre = TestClient(app)
        jeton_autre = _connecter(client_autre, "0341101002")
        refuse = client_autre.post(
            f"/classe/{self.cours_id}/modifier",
            data={
                "_csrf": jeton_autre, "nom": "Cours détourné",
                "matiere": "Finance", "niveau": "L1",
            },
            follow_redirects=False,
        )
        self.assertEqual(refuse.status_code, 303)
        with Session(engine) as session:
            self.assertEqual(session.get(Cours, self.cours_id).nom, "Comptabilité générale")

        client = TestClient(app)
        jeton = _connecter(client, "0341101001")
        accepte = client.post(
            f"/classe/{self.cours_id}/modifier",
            data={
                "_csrf": jeton, "nom": "Comptabilité approfondie",
                "matiere": "Comptabilité", "niveau": "L3",
                "objectifs": "Analyser les opérations complexes.",
            },
            follow_redirects=False,
        )
        self.assertEqual(accepte.status_code, 303)
        with Session(engine) as session:
            cours = session.get(Cours, self.cours_id)
        self.assertEqual(cours.nom, "Comptabilité approfondie")
        self.assertEqual(cours.objectifs, "Analyser les opérations complexes.")

    def test_creation_devoir_valide_le_bareme_et_les_criteres(self):
        client = TestClient(app)
        jeton = _connecter(client, "0341101001")
        reponse = client.post(
            f"/classe/{self.cours_id}/devoirs/creer",
            data={
                "_csrf": jeton,
                "titre": "Étude de cas",
                "description": "Analyser le résultat.",
                "date_limite": "",
                "bareme": "40",
                "criteres": "Analyse | 20\nJustification | 15\nRédaction | 5",
            },
            follow_redirects=False,
        )
        self.assertEqual(reponse.status_code, 303)
        with Session(engine) as session:
            devoir = session.exec(
                select(Devoir).where(Devoir.titre == "Étude de cas")
            ).first()
        self.assertIsNotNone(devoir)
        self.assertEqual(devoir.bareme, 40.0)
        self.assertEqual(len(json.loads(devoir.criteres_json)), 3)

        invalide = client.post(
            f"/classe/{self.cours_id}/devoirs/creer",
            data={
                "_csrf": jeton, "titre": "Barème invalide",
                "bareme": "10", "criteres": "Analyse | 8\nRédaction | 8",
            },
            follow_redirects=False,
        )
        self.assertIn("erreur=devoir_invalide", invalide.headers["location"])
        with Session(engine) as session:
            absent = session.exec(
                select(Devoir).where(Devoir.titre == "Barème invalide")
            ).first()
        self.assertIsNone(absent)

    def test_notation_refuse_une_note_superieure_au_bareme_et_publie_la_note_validee(self):
        with Session(engine) as session:
            rendu = RenduDevoir(
                devoir_id=self.devoir_id,
                utilisateur_id=self.etudiant_id,
                chemin_fichier="uploads/copie-test.pdf",
                nom_fichier_original="copie-test.pdf",
            )
            session.add(rendu)
            session.commit()
            session.refresh(rendu)
            self.rendu_id = rendu.id

        client = TestClient(app)
        jeton = _connecter(client, "0341101001")
        hors_bareme = client.post(
            f"/classe/devoirs/rendus/{self.rendu_id}/noter",
            data={"_csrf": jeton, "note": "31", "appreciation_prof": "Trop haut"},
            follow_redirects=False,
        )
        self.assertIn("erreur=note_hors_bareme", hors_bareme.headers["location"])
        with Session(engine) as session:
            rendu = session.get(RenduDevoir, self.rendu_id)
            self.assertIsNone(rendu.note)
            self.assertIsNone(rendu.date_correction)

        valide = client.post(
            f"/classe/devoirs/rendus/{self.rendu_id}/noter",
            data={
                "_csrf": jeton,
                "note": "28.5",
                "appreciation_prof": "Bonne méthode, vérifie la présentation.",
                "details_correction": "Exactitude : 14/15 ; méthode : 10/10 ; présentation : 4.5/5",
            },
            follow_redirects=False,
        )
        self.assertIn("correction=validee", valide.headers["location"])
        with Session(engine) as session:
            rendu = session.get(RenduDevoir, self.rendu_id)
        self.assertEqual(rendu.note, 28.5)
        self.assertIsNotNone(rendu.date_correction)
        self.assertIn("commentaire_criteres", rendu.details_correction_json)

        etudiant = TestClient(app)
        _connecter(etudiant, "0341101003")
        page = etudiant.get(f"/classe/devoirs/{self.devoir_id}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("28.50", page.text)
        self.assertIn("Bonne méthode", page.text)
        self.assertNotIn("Suggestion IA", page.text)

    def test_suggestion_ia_ne_devient_pas_une_note_officielle(self):
        from app.routers import classe_router

        with Session(engine) as session:
            rendu = RenduDevoir(
                devoir_id=self.devoir_id,
                utilisateur_id=self.etudiant_id,
                chemin_fichier="uploads/copie-a-lire.pdf",
                nom_fichier_original="copie-a-lire.pdf",
            )
            session.add(rendu)
            session.commit()
            session.refresh(rendu)
            self.rendu_id = rendu.id

        @contextmanager
        def faux_fichier(_reference):
            yield Path("/tmp/copie-extraite.pdf")

        suggestion = {
            "note_suggeree": 22.0,
            "bareme": 30.0,
            "appreciation": "La démarche est globalement juste.",
            "criteres": [],
            "forces": ["Calculs cohérents"],
            "ameliorations": ["Mieux présenter les unités"],
            "limites": "Un extrait textuel seulement a été évalué.",
            "confiance": 0.7,
            "statut": "brouillon_a_valider",
            "avertissement": "À valider par le professeur.",
        }
        with patch.object(classe_router, "ouvrir_fichier_local", faux_fichier), \
             patch.object(classe_router, "extraire_texte", lambda _path: "Texte de copie " * 100), \
             patch.object(classe_router.classe_correction, "generer_suggestion_correction", lambda **_kwargs: suggestion):
            client = TestClient(app)
            jeton = _connecter(client, "0341101001")
            reponse = client.post(
                f"/classe/devoirs/rendus/{self.rendu_id}/aide-correction",
                data={"_csrf": jeton},
                follow_redirects=False,
            )
        self.assertIn("ia=proposee", reponse.headers["location"])
        with Session(engine) as session:
            rendu = session.get(RenduDevoir, self.rendu_id)
        self.assertIsNone(rendu.note)
        self.assertIsNone(rendu.date_correction)
        self.assertEqual(json.loads(rendu.correction_ia_json)["note_suggeree"], 22.0)

    def test_suppression_devoir_efface_les_rendus_et_fichiers(self):
        fichier = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        fichier.write(b"fichier de test")
        fichier.close()
        with Session(engine) as session:
            rendu = RenduDevoir(
                devoir_id=self.devoir_id,
                utilisateur_id=self.etudiant_id,
                chemin_fichier=fichier.name,
                nom_fichier_original="copie.pdf",
            )
            session.add(rendu)
            session.commit()

        client = TestClient(app)
        jeton = _connecter(client, "0341101001")
        reponse = client.post(
            f"/classe/devoirs/{self.devoir_id}/supprimer",
            data={"_csrf": jeton, "confirmation": "SUPPRIMER"},
            follow_redirects=False,
        )
        self.assertEqual(reponse.status_code, 303)
        self.assertFalse(Path(fichier.name).exists())
        with Session(engine) as session:
            self.assertIsNone(session.get(Devoir, self.devoir_id))
            rendus = session.exec(
                select(RenduDevoir).where(RenduDevoir.devoir_id == self.devoir_id)
            ).all()
        self.assertEqual(rendus, [])

    def test_barreme_ne_peut_pas_devenir_inferieur_aux_notes_deja_publiees(self):
        with Session(engine) as session:
            session.add(RenduDevoir(
                devoir_id=self.devoir_id,
                utilisateur_id=self.etudiant_id,
                chemin_fichier="uploads/note-existante.pdf",
                nom_fichier_original="note-existante.pdf",
                note=25.0,
            ))
            session.commit()

        client = TestClient(app)
        jeton = _connecter(client, "0341101001")
        reponse = client.post(
            f"/classe/devoirs/{self.devoir_id}/modifier",
            data={
                "_csrf": jeton,
                "titre": "Bilan comptable",
                "description": "Consigne mise à jour.",
                "date_limite": "",
                "bareme": "20",
                "criteres": "Exactitude | 10\nMéthode | 10",
                "etat": "ouvert",
                "archivage": "actif",
            },
            follow_redirects=False,
        )
        self.assertIn("bareme_note_existante", reponse.headers["location"])
        with Session(engine) as session:
            devoir = session.get(Devoir, self.devoir_id)
        self.assertEqual(devoir.bareme, 30.0)

    def test_export_csv_ne_laisse_pas_un_nom_devenir_une_formule(self):
        with Session(engine) as session:
            etudiant = session.get(Utilisateur, self.etudiant_id)
            etudiant.nom = "=HYPERLINK(\"https://example.invalid\")"
            session.add(etudiant)
            session.commit()

        client = TestClient(app)
        _connecter(client, "0341101001")
        reponse = client.get(f"/classe/{self.cours_id}/notes.csv")
        self.assertEqual(reponse.status_code, 200)
        self.assertIn("'=HYPERLINK", reponse.text)


    def test_comptage_inscrits_utilise_une_agregation_sql(self):
        from sqlalchemy import event

        from app.routers.classe_router import _compter_inscrits_cours

        requetes_inscriptions = []

        def capturer_requete(_connexion, _curseur, instruction, _parametres, _contexte, _executemany):
            if "inscriptioncours" in instruction.casefold():
                requetes_inscriptions.append(instruction)

        event.listen(engine, "before_cursor_execute", capturer_requete)
        try:
            with Session(engine) as session:
                nombre = _compter_inscrits_cours(session, self.cours_id)
        finally:
            event.remove(engine, "before_cursor_execute", capturer_requete)

        self.assertEqual(nombre, 1)
        self.assertEqual(len(requetes_inscriptions), 1)
        self.assertIn("count(", requetes_inscriptions[0].casefold())

    def test_templates_classe_compilent(self):
        env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"))
        for nom in ("classe_liste.html", "classe_detail.html", "classe_devoir.html"):
            self.assertIsNotNone(env.get_template(nom))


if __name__ == "__main__":
    unittest.main()
