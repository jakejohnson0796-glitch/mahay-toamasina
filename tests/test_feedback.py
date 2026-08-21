"""
Tests d'integration HTTP (bout en bout, via TestClient) pour le systeme
de feedback : soumission par un utilisateur, validation, rate limiting,
affichage public, et reponse/moderation admin.

Meme pattern que tests/test_messagerie_enrichie.py.

Lancer avec :
    python -m unittest tests.test_feedback -v
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
from app.models import (  # noqa: E402
    Utilisateur, RoleUtilisateur, Feedback, ReponseFeedback, StatutFeedback,
    CategorieFeedback, Notification, TypeNotification,
)
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


class TestFeedback(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        SQLModel.metadata.create_all(engine)

    def setUp(self):
        rate_limit._tentatives.clear()
        with Session(engine) as session:
            for table in (Notification, ReponseFeedback, Feedback, Utilisateur):
                for ligne in session.exec(select(table)).all():
                    session.delete(ligne)
            session.commit()

        self.admin = _creer_client_connecte("0341600001", "Admin FB", role=RoleUtilisateur.ADMIN)
        self.marie = _creer_client_connecte("0341600002", "Marie Rakoto")
        self.jean = _creer_client_connecte("0341600003", "Jean Rabe")
        self.anonyme = TestClient(app)

    # --- Soumission utilisateur ---

    def test_utilisateur_connecte_peut_envoyer_un_feedback(self):
        jeton = _jeton_csrf(self.marie, "/feedback")
        reponse = self.marie.post(
            "/feedback",
            data={"note": 5, "commentaire": "Tres bonne plateforme", "categorie": "general", "est_public": "1", "_csrf": jeton},
            follow_redirects=False,
        )
        self.assertIn(reponse.status_code, (302, 303))
        with Session(engine) as session:
            feedback = session.exec(select(Feedback).where(Feedback.utilisateur_id == self.marie.utilisateur_id)).first()
            self.assertIsNotNone(feedback)
            self.assertEqual(feedback.note, 5)
            self.assertTrue(feedback.est_public)
            self.assertEqual(feedback.statut, StatutFeedback.NOUVEAU)

    def test_anonyme_ne_peut_pas_envoyer_de_feedback(self):
        jeton = _jeton_csrf(self.anonyme, "/connexion")
        reponse = self.anonyme.post(
            "/feedback",
            data={"note": 4, "commentaire": "test", "categorie": "general", "_csrf": jeton},
            follow_redirects=False,
        )
        self.assertIn(reponse.status_code, (302, 303))
        with Session(engine) as session:
            self.assertEqual(len(session.exec(select(Feedback)).all()), 0)

    def test_note_hors_bornes_rejetee(self):
        jeton = _jeton_csrf(self.marie, "/feedback")
        reponse = self.marie.post(
            "/feedback",
            data={"note": 7, "commentaire": "note invalide", "categorie": "general", "_csrf": jeton},
            follow_redirects=False,
        )
        self.assertIn("erreur=note_invalide", reponse.headers.get("location", ""))
        with Session(engine) as session:
            self.assertEqual(len(session.exec(select(Feedback)).all()), 0)

    def test_commentaire_vide_rejete(self):
        jeton = _jeton_csrf(self.marie, "/feedback")
        reponse = self.marie.post(
            "/feedback",
            data={"note": 3, "commentaire": "   ", "categorie": "general", "_csrf": jeton},
            follow_redirects=False,
        )
        self.assertIn("erreur=commentaire_requis", reponse.headers.get("location", ""))

    def test_commentaire_trop_long_rejete(self):
        jeton = _jeton_csrf(self.marie, "/feedback")
        reponse = self.marie.post(
            "/feedback",
            data={"note": 3, "commentaire": "x" * 2000, "categorie": "general", "_csrf": jeton},
            follow_redirects=False,
        )
        self.assertIn("erreur=commentaire_trop_long", reponse.headers.get("location", ""))

    def test_double_soumission_identique_immediate_non_dupliquee(self):
        jeton = _jeton_csrf(self.marie, "/feedback")
        for _ in range(2):
            self.marie.post(
                "/feedback",
                data={"note": 4, "commentaire": "Meme avis envoye deux fois", "categorie": "general", "_csrf": jeton},
            )
        with Session(engine) as session:
            feedbacks = session.exec(
                select(Feedback).where(Feedback.commentaire == "Meme avis envoye deux fois")
            ).all()
            self.assertEqual(len(feedbacks), 1, "un double-clic ne doit pas creer deux lignes identiques")

    def test_rate_limiting_bloque_apres_plusieurs_envois(self):
        jeton = _jeton_csrf(self.marie, "/feedback")
        for i in range(5):
            self.marie.post(
                "/feedback",
                data={"note": 3, "commentaire": f"Avis numero {i}", "categorie": "general", "_csrf": jeton},
            )
        reponse = self.marie.post(
            "/feedback",
            data={"note": 3, "commentaire": "Avis numero 6", "categorie": "general", "_csrf": jeton},
            follow_redirects=False,
        )
        self.assertIn("erreur=trop_de_tentatives", reponse.headers.get("location", ""))

    # --- Affichage public ---

    def test_avis_public_visible_sur_page_feedback(self):
        with Session(engine) as session:
            session.add(Feedback(utilisateur_id=self.marie.utilisateur_id, note=5,
                                  commentaire="Avis visible", categorie=CategorieFeedback.GENERAL, est_public=True))
            session.commit()
        page = self.anonyme.get("/feedback")
        self.assertIn("Avis visible", page.text)

    def test_avis_prive_absent_de_la_page_publique(self):
        with Session(engine) as session:
            session.add(Feedback(utilisateur_id=self.marie.utilisateur_id, note=2,
                                  commentaire="Avis reste prive", categorie=CategorieFeedback.GENERAL, est_public=False))
            session.commit()
        page = self.anonyme.get("/feedback")
        self.assertNotIn("Avis reste prive", page.text)

    # --- Administration ---

    def test_non_admin_ne_peut_pas_acceder_a_la_liste_admin(self):
        reponse = self.jean.get("/admin/feedback", follow_redirects=False)
        self.assertIn(reponse.status_code, (302, 303))

    def test_admin_peut_repondre_a_un_feedback(self):
        with Session(engine) as session:
            fb = Feedback(utilisateur_id=self.marie.utilisateur_id, note=4,
                           commentaire="A ameliorer", categorie=CategorieFeedback.SUGGESTION)
            session.add(fb)
            session.commit()
            session.refresh(fb)
            feedback_id = fb.id

        jeton = _jeton_csrf(self.admin, "/admin/feedback")
        reponse = self.admin.post(
            f"/admin/feedback/{feedback_id}/repondre",
            data={"reponse": "Merci, nous regardons cela.", "_csrf": jeton},
            follow_redirects=False,
        )
        self.assertIn(reponse.status_code, (302, 303))

        with Session(engine) as session:
            fb = session.get(Feedback, feedback_id)
            self.assertEqual(fb.statut, StatutFeedback.REPONDU)
            rep = session.exec(select(ReponseFeedback).where(ReponseFeedback.feedback_id == feedback_id)).first()
            self.assertIsNotNone(rep)
            self.assertEqual(rep.reponse, "Merci, nous regardons cela.")

            # Notification creee pour l'auteur du feedback (reutilise le
            # systeme de notification existant, pas un doublon).
            notif = session.exec(
                select(Notification).where(Notification.destinataire_id == self.marie.utilisateur_id)
            ).first()
            self.assertIsNotNone(notif)
            self.assertEqual(notif.type_notification, TypeNotification.REPONSE_FEEDBACK)

    def test_modifier_une_reponse_existante_ne_duplique_pas(self):
        with Session(engine) as session:
            fb = Feedback(utilisateur_id=self.marie.utilisateur_id, note=4, commentaire="Test")
            session.add(fb)
            session.commit()
            session.refresh(fb)
            feedback_id = fb.id

        jeton = _jeton_csrf(self.admin, "/admin/feedback")
        self.admin.post(f"/admin/feedback/{feedback_id}/repondre", data={"reponse": "Premiere reponse", "_csrf": jeton})
        jeton2 = _jeton_csrf(self.admin, "/admin/feedback")
        self.admin.post(f"/admin/feedback/{feedback_id}/repondre", data={"reponse": "Reponse corrigee", "_csrf": jeton2})

        with Session(engine) as session:
            reponses = session.exec(select(ReponseFeedback).where(ReponseFeedback.feedback_id == feedback_id)).all()
            self.assertEqual(len(reponses), 1)
            self.assertEqual(reponses[0].reponse, "Reponse corrigee")

    def test_non_admin_ne_peut_pas_repondre(self):
        with Session(engine) as session:
            fb = Feedback(utilisateur_id=self.marie.utilisateur_id, note=4, commentaire="Test")
            session.add(fb)
            session.commit()
            session.refresh(fb)
            feedback_id = fb.id

        jeton = _jeton_csrf(self.jean, "/feedback")
        reponse = self.jean.post(
            f"/admin/feedback/{feedback_id}/repondre",
            data={"reponse": "Je ne suis pas admin", "_csrf": jeton},
            follow_redirects=False,
        )
        self.assertIn(reponse.status_code, (302, 303))
        with Session(engine) as session:
            self.assertIsNone(session.exec(select(ReponseFeedback).where(ReponseFeedback.feedback_id == feedback_id)).first())

    def test_admin_peut_masquer_un_avis_public(self):
        with Session(engine) as session:
            fb = Feedback(utilisateur_id=self.marie.utilisateur_id, note=1,
                           commentaire="Avis a masquer", est_public=True)
            session.add(fb)
            session.commit()
            session.refresh(fb)
            feedback_id = fb.id

        jeton = _jeton_csrf(self.admin, "/admin/feedback")
        self.admin.post(f"/admin/feedback/{feedback_id}/masquer", data={"_csrf": jeton})

        with Session(engine) as session:
            self.assertEqual(session.get(Feedback, feedback_id).statut, StatutFeedback.MASQUE)

        page = self.anonyme.get("/feedback")
        self.assertNotIn("Avis a masquer", page.text)

    def test_utilisateur_ne_peut_pas_voir_le_feedback_prive_dun_autre_via_mes_avis(self):
        with Session(engine) as session:
            session.add(Feedback(utilisateur_id=self.marie.utilisateur_id, note=3, commentaire="Feedback de Marie"))
            session.commit()

        page = self.jean.get("/feedback/mes-avis")
        self.assertNotIn("Feedback de Marie", page.text)


if __name__ == "__main__":
    unittest.main()
