"""
Tests d'integration HTTP (bout en bout, via TestClient) pour la FAQ
publique (/faq) et sa gestion admin (/admin/faq).

Meme pattern que tests/test_messagerie_enrichie.py : vraies routes HTTP,
vrai login, vrai jeton CSRF.

Lancer avec :
    python -m unittest tests.test_faq -v
"""
import os
import re
import unittest
import tempfile

_DB_FICHIER = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FICHIER}"
os.environ.setdefault("SESSION_SECRET_KEY", "cle-de-test-uniquement-jamais-en-production")

from starlette.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel, Session, select  # noqa: E402

from app.main import app  # noqa: E402
from app.database import engine  # noqa: E402
from app.auth import hacher_mot_de_passe  # noqa: E402
from app.models import Utilisateur, RoleUtilisateur, FAQ, CategorieFAQ  # noqa: E402
from app import rate_limit  # noqa: E402


def _creer_client_connecte(telephone: str, nom: str, role: RoleUtilisateur = RoleUtilisateur.ETUDIANT) -> TestClient:
    with Session(engine) as session:
        utilisateur = Utilisateur(
            nom=nom,
            telephone=telephone,
            mot_de_passe_hash=hacher_mot_de_passe("MotDePasse123!"),
            role=role,
        )
        session.add(utilisateur)
        session.commit()
        session.refresh(utilisateur)
        utilisateur_id = utilisateur.id

    client = TestClient(app)
    page = client.get("/connexion")
    jeton = re.search(r'name="_csrf" value="([^"]+)"', page.text).group(1)
    reponse = client.post(
        "/connexion",
        data={"telephone": telephone, "mot_de_passe": "MotDePasse123!", "_csrf": jeton},
        follow_redirects=False,
    )
    assert reponse.status_code in (302, 303), f"Connexion echouee : {reponse.status_code} {reponse.text[:300]}"
    client.utilisateur_id = utilisateur_id
    return client


def _jeton_csrf(client: TestClient, url: str) -> str:
    page = client.get(url)
    return re.search(r'name="_csrf" value="([^"]+)"', page.text).group(1)


class TestFaqPublique(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        SQLModel.metadata.create_all(engine)

    def setUp(self):
        rate_limit._tentatives.clear()
        with Session(engine) as session:
            for table in (FAQ, Utilisateur):
                for ligne in session.exec(select(table)).all():
                    session.delete(ligne)
            session.commit()

            session.add_all([
                FAQ(question="Comment creer un compte ?", reponse="Rendez-vous sur la page d'inscription.",
                    categorie=CategorieFAQ.COMPTE, est_active=True, ordre_affichage=0),
                FAQ(question="Qu'est-ce qu'un cercle d'etude ?", reponse="Un espace de revision en groupe.",
                    categorie=CategorieFAQ.CERCLES, est_active=True, ordre_affichage=1),
                FAQ(question="Question retiree", reponse="Ne doit jamais apparaitre publiquement.",
                    categorie=CategorieFAQ.GENERAL, est_active=False, ordre_affichage=2),
            ])
            session.commit()

        self.anonyme = TestClient(app)
        self.admin = _creer_client_connecte("0341500001", "Admin FAQ", role=RoleUtilisateur.ADMIN)
        self.etudiant = _creer_client_connecte("0341500002", "Etudiant Lambda")

    def test_page_faq_liste_uniquement_les_questions_actives(self):
        page = self.anonyme.get("/faq")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Comment creer un compte ?", page.text)
        self.assertNotIn("Question retiree", page.text)

    def test_recherche_insensible_a_la_casse(self):
        page = self.anonyme.get("/faq", params={"q": "CERCLE"})
        self.assertEqual(page.status_code, 200)
        self.assertIn("cercle d", page.text.lower())
        self.assertNotIn("Comment creer un compte ?", page.text)

    def test_recherche_sans_resultat(self):
        page = self.anonyme.get("/faq", params={"q": "xyzabc_inexistant"})
        self.assertEqual(page.status_code, 200)
        self.assertNotIn("Comment creer un compte ?", page.text)

    def test_filtre_par_categorie(self):
        page = self.anonyme.get("/faq", params={"categorie": "cercles"})
        self.assertIn("Qu", page.text)
        self.assertNotIn("Comment creer un compte ?", page.text)

    # --- Administration ---

    def test_non_admin_ne_peut_pas_acceder_a_la_gestion_faq(self):
        reponse = self.etudiant.get("/admin/faq", follow_redirects=False)
        self.assertIn(reponse.status_code, (302, 303))

    def test_admin_peut_creer_une_question(self):
        jeton = _jeton_csrf(self.admin, "/admin/faq")
        reponse = self.admin.post(
            "/admin/faq",
            data={"question": "Nouvelle question", "reponse": "Nouvelle reponse",
                  "categorie": "general", "ordre_affichage": 5, "_csrf": jeton},
            follow_redirects=False,
        )
        self.assertIn(reponse.status_code, (302, 303))
        with Session(engine) as session:
            faq = session.exec(select(FAQ).where(FAQ.question == "Nouvelle question")).first()
            self.assertIsNotNone(faq)
            self.assertEqual(faq.categorie, CategorieFAQ.GENERAL)

    def test_non_admin_ne_peut_pas_creer_une_question(self):
        jeton = _jeton_csrf(self.etudiant, "/feedback")
        reponse = self.etudiant.post(
            "/admin/faq",
            data={"question": "Injection", "reponse": "Ne doit pas passer",
                  "categorie": "general", "ordre_affichage": 0, "_csrf": jeton},
            follow_redirects=False,
        )
        self.assertIn(reponse.status_code, (302, 303))
        with Session(engine) as session:
            self.assertIsNone(session.exec(select(FAQ).where(FAQ.question == "Injection")).first())

    def test_admin_peut_desactiver_puis_reactiver(self):
        with Session(engine) as session:
            faq_id = session.exec(select(FAQ).where(FAQ.question == "Comment creer un compte ?")).first().id

        jeton = _jeton_csrf(self.admin, "/admin/faq")
        self.admin.post(f"/admin/faq/{faq_id}/basculer-actif", data={"_csrf": jeton})
        with Session(engine) as session:
            self.assertFalse(session.get(FAQ, faq_id).est_active)

        jeton2 = _jeton_csrf(self.admin, "/admin/faq")
        self.admin.post(f"/admin/faq/{faq_id}/basculer-actif", data={"_csrf": jeton2})
        with Session(engine) as session:
            self.assertTrue(session.get(FAQ, faq_id).est_active)

    def test_suppression_est_logique_pas_physique(self):
        with Session(engine) as session:
            faq_id = session.exec(select(FAQ).where(FAQ.question == "Comment creer un compte ?")).first().id

        jeton = _jeton_csrf(self.admin, "/admin/faq")
        self.admin.post(f"/admin/faq/{faq_id}/supprimer", data={"_csrf": jeton})

        with Session(engine) as session:
            faq = session.get(FAQ, faq_id)
            self.assertIsNotNone(faq, "la ligne doit toujours exister en base (suppression logique)")
            self.assertFalse(faq.est_active)

        # Et elle disparait bien de la vue publique.
        page = self.anonyme.get("/faq")
        self.assertNotIn("Comment creer un compte ?", page.text)

    def test_creation_rejette_question_vide(self):
        jeton = _jeton_csrf(self.admin, "/admin/faq")
        reponse = self.admin.post(
            "/admin/faq",
            data={"question": "   ", "reponse": "reponse", "categorie": "general",
                  "ordre_affichage": 0, "_csrf": jeton},
            follow_redirects=False,
        )
        self.assertIn(reponse.status_code, (302, 303))
        self.assertIn("erreur=champs_requis", reponse.headers.get("location", ""))


if __name__ == "__main__":
    unittest.main()
