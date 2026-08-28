"""
Test d'integration HTTP du rendu de la page /cercles/{id} (template
cercle_chat.html) avec des messages, reactions, epinglage et reponses
deja en base : verifie que le template Jinja rend sans erreur et que
les elements cles de la messagerie enrichie (session 3, frontend) sont
bien presents dans le HTML genere.

Complementaire a test_messagerie_enrichie.py (qui teste les routes/API),
celui-ci teste specifiquement le rendu du template — une erreur Jinja
(variable manquante, filtre invalide...) ne serait pas detectee par des
tests d'API seuls puisque salon_cercle() est justement la route qui
appelle templates.TemplateResponse().

Lancer avec :
    python -m unittest tests.test_rendu_chat_cercle -v
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
from datetime import datetime, timedelta  # noqa: E402

from app.main import app  # noqa: E402
from app.database import engine  # noqa: E402
from app.auth import hacher_mot_de_passe  # noqa: E402
from app import rate_limit  # noqa: E402
from app.models import (  # noqa: E402
    Utilisateur, RoleUtilisateur, CercleEtude, MembreCercle, RoleMembreCercle,
    MessageCercle, MessageReaction, TypeReaction, StatutCercle,
    AbonnementEtudiant, StatutAbonnementEtudiant,
)


class TestRenduChatCercle(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        SQLModel.metadata.create_all(engine)

    def setUp(self):
        rate_limit._tentatives.clear()
        with Session(engine) as session:
            for table in (MessageReaction, MessageCercle, MembreCercle, AbonnementEtudiant, CercleEtude, Utilisateur):
                for ligne in session.exec(select(table)).all():
                    session.delete(ligne)
            session.commit()

            sarah = Utilisateur(nom="Sarah", telephone="0341000001", mot_de_passe_hash=hacher_mot_de_passe("MotDePasse123!"))
            thomas = Utilisateur(nom="Thomas", telephone="0341000002", mot_de_passe_hash=hacher_mot_de_passe("MotDePasse123!"))
            session.add(sarah)
            session.add(thomas)
            session.commit()
            session.refresh(sarah)
            session.refresh(thomas)
            # Un salon de cercle est une fonctionnalite Premium : sans
            # abonnement (meme en essai), salon_cercle() redirige vers
            # /abonnement avant meme d'atteindre le rendu du template.
            session.add(AbonnementEtudiant(
                utilisateur_id=sarah.id,
                statut=StatutAbonnementEtudiant.ESSAI,
                date_fin_essai=datetime.utcnow() + timedelta(days=14),
            ))
            session.commit()

            cercle = CercleEtude(nom="L2 Gestion / Finance", createur_id=sarah.id, statut=StatutCercle.ACTIF)
            session.add(cercle)
            session.commit()
            session.refresh(cercle)
            self.cercle_id = cercle.id
            session.add(MembreCercle(cercle_id=cercle.id, utilisateur_id=sarah.id, role=RoleMembreCercle.CREATEUR))
            session.add(MembreCercle(cercle_id=cercle.id, utilisateur_id=thomas.id, role=RoleMembreCercle.MEMBRE))
            session.commit()

            message = MessageCercle(
                cercle_id=cercle.id, auteur_id=sarah.id,
                contenu="Quelqu'un a compris l'exercice 4 ?",
                epingle=True, epingle_par_id=sarah.id,
            )
            session.add(message)
            session.commit()
            session.refresh(message)
            self.message_id = message.id
            session.add(MessageReaction(message_id=message.id, utilisateur_id=thomas.id, type_reaction=TypeReaction.POUCE))
            reponse = MessageCercle(cercle_id=cercle.id, auteur_id=thomas.id, contenu="Oui, methode des unites d'oeuvre", parent_message_id=message.id)
            session.add(reponse)
            session.commit()

        self.client = TestClient(app)
        page = self.client.get("/connexion")
        jeton = re.search(r'name="_csrf" value="([^"]+)"', page.text).group(1)
        reponse_connexion = self.client.post(
            "/connexion",
            data={"telephone": "0341000001", "mot_de_passe": "MotDePasse123!", "_csrf": jeton},
            follow_redirects=False,
        )
        assert reponse_connexion.status_code in (302, 303)

    def test_page_du_salon_se_rend_sans_erreur(self):
        reponse = self.client.get(f"/cercles/{self.cercle_id}")
        self.assertEqual(reponse.status_code, 200)

    def test_message_et_son_contenu_sont_affiches(self):
        reponse = self.client.get(f"/cercles/{self.cercle_id}")
        self.assertIn("Quelqu", reponse.text)
        self.assertIn("Sarah", reponse.text)

    def test_reaction_est_affichee(self):
        reponse = self.client.get(f"/cercles/{self.cercle_id}")
        self.assertIn("puce-reaction", reponse.text)
        self.assertIn("👍 1", reponse.text)

    def test_message_epingle_apparait_dans_la_banniere(self):
        reponse = self.client.get(f"/cercles/{self.cercle_id}")
        self.assertIn('id="banniere-epinglee"', reponse.text)
        self.assertIn("message-epingle", reponse.text)
        self.assertNotIn('id="banniere-epinglee" class="message-epingle-banniere" hidden', reponse.text)

    def test_reponse_nest_pas_dans_le_flux_principal_mais_le_compteur_lest(self):
        reponse = self.client.get(f"/cercles/{self.cercle_id}")
        # La reponse (parent_message_id renseigne) n'apparait toujours pas
        # comme une bulle de message a part entiere dans le flux principal
        # (elle vit dans le panneau de thread, charge a la demande) — mais
        # depuis la refonte visuelle du salon, un court apercu (auteur +
        # debut du contenu) figure desormais a cote du compteur "N
        # reponses", pour donner un avant-gout du fil sans l'ouvrir.
        self.assertIn("💬 1 réponse", reponse.text)
        self.assertIn("methode des unites", reponse.text.lower())
        self.assertIn("thread-apercu", reponse.text)

    def test_donnees_mentions_embarquees_pour_lautocompletion(self):
        reponse = self.client.get(f"/cercles/{self.cercle_id}")
        self.assertIn("membresPourMentions", reponse.text)
        self.assertIn("Thomas", reponse.text)

    def test_route_thread_renvoie_bien_la_reponse(self):
        reponse = self.client.get(f"/cercles/{self.cercle_id}/messages/{self.message_id}/thread")
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.json()
        self.assertEqual(len(corps["reponses"]), 1)
        self.assertIn("unites d'oeuvre", corps["reponses"][0]["contenu"])


if __name__ == "__main__":
    unittest.main()
