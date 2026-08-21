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
from app.models import (  # noqa: E402
    Utilisateur, RoleUtilisateur, CercleEtude, MembreCercle, RoleMembreCercle,
    MessageCercle, MessageReaction, MessageMention, Notification, StatutCercle,
)
from app import rate_limit  # noqa: E402


def _creer_client_connecte(telephone: str, nom: str) -> TestClient:
    """Cree un utilisateur directement en base (plus rapide et plus
    fiable qu'un vrai flux d'inscription pour ce qui nous interesse ici),
    puis se connecte via la vraie route /connexion pour obtenir une
    session HTTP authentique et un jeton CSRF valide."""
    with Session(engine) as session:
        utilisateur = Utilisateur(
            nom=nom,
            telephone=telephone,
            mot_de_passe_hash=hacher_mot_de_passe("MotDePasse123!"),
            role=RoleUtilisateur.ETUDIANT,
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
