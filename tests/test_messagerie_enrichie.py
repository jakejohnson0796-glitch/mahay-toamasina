"""
Tests d'integration HTTP (bout en bout, via TestClient) pour la premiere
brique backend de la messagerie enrichie des cercles : reactions,
reponses/thread, edition, epinglage, et les permissions associees.

Contrairement aux autres fichiers de tests du projet (qui testent la
logique metier au niveau ORM, independamment de FastAPI), ceux-ci passent
par les vraies routes HTTP avec un vrai login et un vrai jeton CSRF : ce
sont ces routes elles-memes (permissions incluses) qu'on veut valider ici,
pas une reimplementation de leur logique.

Lancer avec :
    python -m unittest tests.test_messagerie_enrichie -v
"""
import os
import re
import unittest
import tempfile

# DATABASE_URL doit etre fixee AVANT le premier import de app.* (le moteur
# SQLAlchemy est cree une fois au niveau module dans app/database.py).
_DB_FICHIER = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FICHIER}"
os.environ.setdefault("SESSION_SECRET_KEY", "cle-de-test-uniquement-jamais-en-production")

from starlette.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel, Session, select  # noqa: E402

from app.main import app  # noqa: E402
from app.database import engine  # noqa: E402
from app.auth import hacher_mot_de_passe  # noqa: E402
from app.admin_security import action_admin_protegee  # noqa: E402
from app.models import (  # noqa: E402
    Utilisateur, RoleUtilisateur, CercleEtude, MembreCercle, RoleMembreCercle,
    MessageCercle, MessageReaction, MessageMention, Notification, StatutCercle,
    AbonnementEtudiant,
)
from app import rate_limit  # noqa: E402


def _creer_client_connecte(
    telephone: str,
    nom: str,
    role: RoleUtilisateur = RoleUtilisateur.ETUDIANT,
) -> TestClient:
    """Cree un utilisateur directement en base (plus rapide et plus
    fiable qu'un vrai flux d'inscription pour ce qui nous interesse ici),
    puis se connecte via la vraie route /connexion pour obtenir une
    session HTTP authentique et un jeton CSRF valide."""
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
    client.utilisateur_id = utilisateur_id  # pratique pour les assertions
    return client


def _jeton_csrf(client: TestClient, url: str) -> str:
    page = client.get(url)
    return re.search(r'name="_csrf" value="([^"]+)"', page.text).group(1)


class TestMessagerieEnrichie(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        SQLModel.metadata.create_all(engine)

    def setUp(self):
        rate_limit._tentatives.clear()

        # Isolation entre tests : on vide juste les tables qui nous
        # concernent (create_all une seule fois suffit, les tables
        # existent deja) plutot que de recreer toute la base a chaque
        # test — plus rapide, et aucun autre test du projet ne partage
        # ce fichier SQLite temporaire.
        with Session(engine) as session:
            for table in (Notification, MessageMention, MessageReaction, MessageCercle, MembreCercle, CercleEtude, Utilisateur):
                for ligne in session.exec(select(table)).all():
                    session.delete(ligne)
            session.commit()

        self.sarah = _creer_client_connecte("0341000001", "Sarah")
        self.thomas = _creer_client_connecte("0341000002", "Thomas")
        self.intrus = _creer_client_connecte("0341000003", "Intrus")  # jamais ajoute au cercle

        with Session(engine) as session:
            cercle = CercleEtude(nom="L2 Gestion / Finance", createur_id=self.sarah.utilisateur_id, statut=StatutCercle.ACTIF)
            session.add(cercle)
            session.commit()
            session.refresh(cercle)
            self.cercle_id = cercle.id
            session.add(MembreCercle(cercle_id=cercle.id, utilisateur_id=self.sarah.utilisateur_id, role=RoleMembreCercle.CREATEUR))
            session.add(MembreCercle(cercle_id=cercle.id, utilisateur_id=self.thomas.utilisateur_id, role=RoleMembreCercle.MEMBRE))
            session.commit()

            message = MessageCercle(cercle_id=cercle.id, auteur_id=self.sarah.utilisateur_id, contenu="Quelqu'un a compris l'exercice 4 ?")
            session.add(message)
            session.commit()
            session.refresh(message)
            self.message_id = message.id

    def test_administrateur_peut_utiliser_websocket_sans_abonnement_etudiant(self):
        administrateur = _creer_client_connecte(
            "0341000004", "Admin de test", role=RoleUtilisateur.ADMIN
        )

        # Garantit que ce test couvre bien l'exemption admin, meme si le
        # parcours de connexion venait a creer un abonnement par defaut.
        with Session(engine) as session:
            for abonnement in session.exec(
                select(AbonnementEtudiant).where(
                    AbonnementEtudiant.utilisateur_id == administrateur.utilisateur_id
                )
            ).all():
                session.delete(abonnement)
            session.commit()

        statut_acces = administrateur.get(f"/cercles/{self.cercle_id}/ws-status")
        self.assertEqual(statut_acces.status_code, 200)
        self.assertTrue(statut_acces.json()["ok"])

        with administrateur.websocket_connect(f"/cercles/{self.cercle_id}/ws") as websocket:
            presence = websocket.receive_json()
            self.assertEqual(presence["type"], "presence")

            websocket.send_json({"contenu": "Message admin sans abonnement"})
            message = websocket.receive_json()
            self.assertEqual(message["type"], "message")
            self.assertEqual(message["contenu"], "Message admin sans abonnement")

        with Session(engine) as session:
            message_stocke = session.exec(
                select(MessageCercle).where(
                    MessageCercle.cercle_id == self.cercle_id,
                    MessageCercle.auteur_id == administrateur.utilisateur_id,
                    MessageCercle.contenu == "Message admin sans abonnement",
                )
            ).first()
            self.assertIsNotNone(message_stocke)

    def test_administrateur_peut_supprimer_son_propre_message_sans_confirmation_admin(self):
        administrateur = _creer_client_connecte(
            "0341000005", "Admin supprimant son message", role=RoleUtilisateur.ADMIN
        )

        # Cette action ordinaire du salon ne doit pas demander le secret de
        # confirmation réservé aux actions d'administration sensibles.
        with Session(engine) as session:
            message = MessageCercle(
                cercle_id=self.cercle_id,
                auteur_id=administrateur.utilisateur_id,
                contenu="Message admin à supprimer",
            )
            session.add(message)
            session.commit()
            session.refresh(message)
            message_id = message.id

        jeton = _jeton_csrf(administrateur, f"/cercles/{self.cercle_id}")
        reponse = administrateur.post(
            f"/cercles/{self.cercle_id}/messages/{message_id}/supprimer",
            data={"_csrf": jeton},
            follow_redirects=False,
        )
        self.assertEqual(reponse.status_code, 303, reponse.text)
        self.assertEqual(reponse.headers.get("location"), f"/cercles/{self.cercle_id}")

        with Session(engine) as session:
            message_stocke = session.get(MessageCercle, message_id)
            self.assertIsNotNone(message_stocke)
            self.assertTrue(message_stocke.supprime)

    def test_confirmation_admin_ne_cible_pas_la_suppression_message(self):
        self.assertFalse(
            action_admin_protegee(f"/cercles/{self.cercle_id}/messages/{self.message_id}/supprimer")
        )

    def test_confirmation_admin_protege_toujours_la_suppression_cercle(self):
        self.assertTrue(action_admin_protegee(f"/cercles/{self.cercle_id}/supprimer"))

    def test_preflight_refuse_un_non_membre_avec_une_raison_stable(self):
        reponse = self.intrus.get(f"/cercles/{self.cercle_id}/ws-status")
        self.assertEqual(reponse.status_code, 403)
        self.assertEqual(reponse.json(), {"ok": False, "code": "membership_required"})

    def test_preflight_signale_le_premium_expire_pour_un_membre(self):
        reponse = self.thomas.get(f"/cercles/{self.cercle_id}/ws-status")
        self.assertEqual(reponse.status_code, 402)
        self.assertEqual(reponse.json(), {"ok": False, "code": "premium_required"})

    # --- Reactions ---

    def test_ajouter_une_reaction(self):
        jeton = _jeton_csrf(self.thomas, f"/cercles/{self.cercle_id}")
        reponse = self.thomas.post(
            f"/cercles/{self.cercle_id}/messages/{self.message_id}/reaction",
            data={"type_reaction": "pouce", "_csrf": jeton},
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()["reactions"], [{"type_reaction": "pouce", "total": 1, "mienne": True}])

        with Session(engine) as session:
            self.assertEqual(
                session.exec(select(Notification).where(Notification.destinataire_id == self.sarah.utilisateur_id)).all().__len__(),
                1,
                "l'auteur du message doit etre notifie de la reaction",
            )

    def test_re_cliquer_la_meme_reaction_la_retire(self):
        jeton = _jeton_csrf(self.thomas, f"/cercles/{self.cercle_id}")
        self.thomas.post(f"/cercles/{self.cercle_id}/messages/{self.message_id}/reaction", data={"type_reaction": "pouce", "_csrf": jeton})
        reponse = self.thomas.post(f"/cercles/{self.cercle_id}/messages/{self.message_id}/reaction", data={"type_reaction": "pouce", "_csrf": jeton})
        self.assertEqual(reponse.json()["reactions"], [])

    def test_changer_de_reaction_remplace_lancienne(self):
        jeton = _jeton_csrf(self.thomas, f"/cercles/{self.cercle_id}")
        self.thomas.post(f"/cercles/{self.cercle_id}/messages/{self.message_id}/reaction", data={"type_reaction": "pouce", "_csrf": jeton})
        reponse = self.thomas.post(f"/cercles/{self.cercle_id}/messages/{self.message_id}/reaction", data={"type_reaction": "coeur", "_csrf": jeton})
        self.assertEqual(reponse.json()["reactions"], [{"type_reaction": "coeur", "total": 1, "mienne": True}])

    def test_utilisateur_hors_cercle_ne_peut_pas_reagir(self):
        jeton = _jeton_csrf(self.intrus, f"/cercles/{self.cercle_id}")
        reponse = self.intrus.post(f"/cercles/{self.cercle_id}/messages/{self.message_id}/reaction", data={"type_reaction": "pouce", "_csrf": jeton})
        self.assertEqual(reponse.status_code, 403)

    def test_type_reaction_invalide_rejete(self):
        jeton = _jeton_csrf(self.thomas, f"/cercles/{self.cercle_id}")
        reponse = self.thomas.post(f"/cercles/{self.cercle_id}/messages/{self.message_id}/reaction", data={"type_reaction": "n_importe_quoi", "_csrf": jeton})
        self.assertEqual(reponse.status_code, 400)

    # --- Edition ---

    def test_auteur_peut_modifier_son_message(self):
        jeton = _jeton_csrf(self.sarah, f"/cercles/{self.cercle_id}")
        reponse = self.sarah.post(
            f"/cercles/{self.cercle_id}/messages/{self.message_id}/modifier",
            data={"contenu": "Correction : exercice 5, pas 4 !", "_csrf": jeton},
        )
        self.assertEqual(reponse.status_code, 200)
        with Session(engine) as session:
            message = session.get(MessageCercle, self.message_id)
            self.assertEqual(message.contenu, "Correction : exercice 5, pas 4 !")
            self.assertIsNotNone(message.date_modification)

    def test_autre_membre_ne_peut_pas_modifier(self):
        jeton = _jeton_csrf(self.thomas, f"/cercles/{self.cercle_id}")
        reponse = self.thomas.post(
            f"/cercles/{self.cercle_id}/messages/{self.message_id}/modifier",
            data={"contenu": "Je modifie le message de Sarah", "_csrf": jeton},
        )
        self.assertEqual(reponse.status_code, 403)

    # --- Epinglage ---

    def test_createur_du_cercle_peut_epingler(self):
        jeton = _jeton_csrf(self.sarah, f"/cercles/{self.cercle_id}")
        reponse = self.sarah.post(f"/cercles/{self.cercle_id}/messages/{self.message_id}/epingler", data={"_csrf": jeton})
        self.assertEqual(reponse.status_code, 200)
        with Session(engine) as session:
            self.assertTrue(session.get(MessageCercle, self.message_id).epingle)

    def test_simple_membre_ne_peut_pas_epingler(self):
        jeton = _jeton_csrf(self.thomas, f"/cercles/{self.cercle_id}")
        reponse = self.thomas.post(f"/cercles/{self.cercle_id}/messages/{self.message_id}/epingler", data={"_csrf": jeton})
        self.assertEqual(reponse.status_code, 403)

    def test_epingler_un_nouveau_message_desepingle_lancien(self):
        with Session(engine) as session:
            second = MessageCercle(cercle_id=self.cercle_id, auteur_id=self.thomas.utilisateur_id, contenu="Deuxieme message")
            session.add(second)
            session.commit()
            session.refresh(second)
            second_id = second.id

        jeton = _jeton_csrf(self.sarah, f"/cercles/{self.cercle_id}")
        self.sarah.post(f"/cercles/{self.cercle_id}/messages/{self.message_id}/epingler", data={"_csrf": jeton})
        self.sarah.post(f"/cercles/{self.cercle_id}/messages/{second_id}/epingler", data={"_csrf": jeton})

        with Session(engine) as session:
            self.assertFalse(session.get(MessageCercle, self.message_id).epingle)
            self.assertTrue(session.get(MessageCercle, second_id).epingle)

    # --- Reponses / thread (via websocket, cree directement en base ici
    # pour tester l'endpoint de lecture du thread ; le flux d'envoi via
    # websocket est teste separement en session 3 avec le frontend) ---

    def test_thread_liste_les_reponses_a_un_message(self):
        with Session(engine) as session:
            reponse1 = MessageCercle(cercle_id=self.cercle_id, auteur_id=self.thomas.utilisateur_id, contenu="Methode des unites d'oeuvre", parent_message_id=self.message_id)
            session.add(reponse1)
            session.commit()

        page = self.sarah.get(f"/cercles/{self.cercle_id}/messages/{self.message_id}/thread")
        self.assertEqual(page.status_code, 200)
        corps = page.json()
        self.assertEqual(corps["parent"]["id"], self.message_id)
        self.assertEqual(len(corps["reponses"]), 1)
        self.assertEqual(corps["reponses"][0]["contenu"], "Methode des unites d'oeuvre")

    def test_thread_inaccessible_a_un_non_membre(self):
        reponse = self.intrus.get(f"/cercles/{self.cercle_id}/messages/{self.message_id}/thread")
        self.assertEqual(reponse.status_code, 403)


if __name__ == "__main__":
    unittest.main()
