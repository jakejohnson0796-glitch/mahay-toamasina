"""
Tests d'integration pour l'affichage de la VRAIE photo de profil (au lieu
de l'initiale+couleur codee en dur) dans le chat des cercles d'etude, et
pour la fiche de profil ouverte au clic sur un avatar.

Couvre les points demandes lors du diagnostic :
- un auteur avec photo -> <img src="/profil/photo/{id}"> dans sa bulle ;
- un auteur sans photo -> repli initiale+couleur inchange ;
- l'avatar affiche correspond a l'AUTEUR du message, jamais a la
  personne connectee qui regarde l'ecran ;
- la meme logique s'applique au rendu initial (HTTP), au fil de
  discussion (/thread) et aux messages diffuses en direct (WebSocket) ;
- /cercles/{id}/membres/{utilisateur_id}/profil renvoie les infos
  publiques attendues, et reste reserve aux membres du meme cercle.

Complementaire a test_rendu_chat_cercle.py (structure de fixture reprise
a l'identique) et a test_messagerie_enrichie.py.

Lancer avec :
    python -m unittest tests.test_avatars_photos_cercle -v
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
    Utilisateur, CercleEtude, MembreCercle, RoleMembreCercle, MessageCercle,
    AbonnementEtudiant, StatutAbonnementEtudiant, StatutCercle, Universite, Faculte, Filiere, Mention,
)


class TestAvatarsPhotosCercle(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        SQLModel.metadata.create_all(engine)

    def setUp(self):
        rate_limit._tentatives.clear()
        with Session(engine) as session:
            for table in (
                MessageCercle, MembreCercle, AbonnementEtudiant, CercleEtude,
                Filiere, Faculte, Mention, Universite, Utilisateur,
            ):
                for ligne in session.exec(select(table)).all():
                    session.delete(ligne)
            session.commit()

            universite = Universite(nom="Universite de Toamasina")
            session.add(universite)
            session.commit()
            session.refresh(universite)

            faculte = Faculte(nom="Faculte des Sciences", universite_id=universite.id)
            session.add(faculte)
            session.commit()
            session.refresh(faculte)

            mention = Mention(nom="Informatique")
            session.add(mention)
            session.commit()
            session.refresh(mention)

            filiere = Filiere(nom="Developpement Web", faculte_id=faculte.id, mention_id=mention.id)
            session.add(filiere)
            session.commit()
            session.refresh(filiere)

            # Sarah a une VRAIE photo (photo_chemin renseigne) ; Thomas
            # n'en a pas encore uploade -- exactement le cas "avec/sans
            # photo" attendu par le repli initiale+couleur.
            sarah = Utilisateur(
                nom="Sarah", telephone="0341000001",
                mot_de_passe_hash=hacher_mot_de_passe("MotDePasse123!"),
                photo_chemin="avatars/sarah.jpg",
                universite_id=universite.id, filiere_id=filiere.id, niveau="L2",
            )
            thomas = Utilisateur(nom="Thomas", telephone="0341000002", mot_de_passe_hash=hacher_mot_de_passe("MotDePasse123!"))
            exterieur = Utilisateur(nom="Elodie", telephone="0341000003", mot_de_passe_hash=hacher_mot_de_passe("MotDePasse123!"))
            session.add(sarah)
            session.add(thomas)
            session.add(exterieur)
            session.commit()
            session.refresh(sarah)
            session.refresh(thomas)
            session.refresh(exterieur)
            self.sarah_id = sarah.id
            self.thomas_id = thomas.id
            self.exterieur_id = exterieur.id

            for u in (sarah, thomas):
                session.add(AbonnementEtudiant(
                    utilisateur_id=u.id,
                    statut=StatutAbonnementEtudiant.ESSAI,
                    date_fin_essai=datetime.utcnow() + timedelta(days=14),
                ))
            session.commit()

            cercle = CercleEtude(nom="L2 Informatique", createur_id=sarah.id, statut=StatutCercle.ACTIF)
            session.add(cercle)
            session.commit()
            session.refresh(cercle)
            self.cercle_id = cercle.id
            session.add(MembreCercle(cercle_id=cercle.id, utilisateur_id=sarah.id, role=RoleMembreCercle.CREATEUR))
            session.add(MembreCercle(cercle_id=cercle.id, utilisateur_id=thomas.id, role=RoleMembreCercle.MEMBRE))
            session.commit()

            message_sarah = MessageCercle(cercle_id=cercle.id, auteur_id=sarah.id, contenu="Message de Sarah, avec photo")
            message_thomas = MessageCercle(cercle_id=cercle.id, auteur_id=thomas.id, contenu="Message de Thomas, sans photo")
            session.add(message_sarah)
            session.add(message_thomas)
            session.commit()
            session.refresh(message_sarah)
            self.message_sarah_id = message_sarah.id
            reponse = MessageCercle(cercle_id=cercle.id, auteur_id=sarah.id, contenu="Reponse de Sarah", parent_message_id=message_sarah.id)
            session.add(reponse)
            session.commit()

        self.client = TestClient(app)

    def _connecter(self, telephone):
        page = self.client.get("/connexion")
        jeton = re.search(r'name="_csrf" value="([^"]+)"', page.text).group(1)
        reponse = self.client.post(
            "/connexion",
            data={"telephone": telephone, "mot_de_passe": "MotDePasse123!", "_csrf": jeton},
            follow_redirects=False,
        )
        assert reponse.status_code in (302, 303), reponse.text

    # ---------- Rendu initial (HTTP) ----------

    def test_auteur_avec_photo_affiche_une_vraie_image(self):
        self._connecter("0341000002")  # Thomas regarde le salon
        reponse = self.client.get(f"/cercles/{self.cercle_id}")
        self.assertIn(f'<img src="/profil/photo/{self.sarah_id}"', reponse.text)

    def test_auteur_sans_photo_garde_le_repli_initiale(self):
        self._connecter("0341000001")  # Sarah regarde le salon
        reponse = self.client.get(f"/cercles/{self.cercle_id}")
        # Le message de Thomas (sans photo) ne doit PAS pointer vers une
        # image -- juste le repli initiale+couleur habituel.
        self.assertNotIn(f'<img src="/profil/photo/{self.thomas_id}"', reponse.text)

    def test_lavatar_correspond_a_lauteur_pas_a_la_personne_connectee(self):
        # Connecte en Thomas (qui n'a pas de photo) : le message de Sarah
        # doit quand meme pointer vers LA PHOTO DE SARAH, pas vers celle
        # (inexistante) de Thomas, ni rester sur un repli initiale par
        # simple prudence.
        self._connecter("0341000002")
        reponse = self.client.get(f"/cercles/{self.cercle_id}")
        bulle_sarah = re.search(
            r'data-message-id="\d+"[^>]*data-auteur-id="' + str(self.sarah_id) + r'".*?</div>\s*</div>',
            reponse.text, re.S,
        )
        self.assertIsNotNone(bulle_sarah, "Bulle du message de Sarah introuvable dans le HTML")
        self.assertIn(f'/profil/photo/{self.sarah_id}', bulle_sarah.group(0))

    def test_bouton_avatar_porte_lid_de_lauteur_pour_le_clic_profil(self):
        self._connecter("0341000001")
        reponse = self.client.get(f"/cercles/{self.cercle_id}")
        self.assertIn(f'data-utilisateur-id="{self.thomas_id}"', reponse.text)

    # ---------- Fil de discussion (/thread) ----------

    def test_thread_indique_si_lauteur_a_une_photo(self):
        self._connecter("0341000002")
        reponse = self.client.get(f"/cercles/{self.cercle_id}/messages/{self.message_sarah_id}/thread")
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.json()
        self.assertTrue(corps["parent"]["auteur_photo"])
        self.assertTrue(corps["reponses"][0]["auteur_photo"])  # reponse de Sarah aussi

    # ---------- WebSocket (messages en direct) ----------

    def test_websocket_diffuse_lindicateur_photo_de_lauteur(self):
        self._connecter("0341000001")  # Sarah, qui a une photo
        with self.client.websocket_connect(f"/cercles/{self.cercle_id}/ws") as ws:
            premiere = ws.receive_json()
            self.assertEqual(premiere["type"], "presence")
            ws.send_json({"contenu": "Un nouveau message en direct"})
            message = ws.receive_json()
            self.assertEqual(message["type"], "message")
            self.assertEqual(message["auteur_id"], self.sarah_id)
            self.assertTrue(message["auteur_photo"])

    def test_websocket_indique_labsence_de_photo(self):
        self._connecter("0341000002")  # Thomas, sans photo
        with self.client.websocket_connect(f"/cercles/{self.cercle_id}/ws") as ws:
            ws.receive_json()  # presence
            ws.send_json({"contenu": "Message de Thomas en direct"})
            message = ws.receive_json()
            self.assertFalse(message["auteur_photo"])

    # ---------- Fiche de profil publique ----------

    def test_fiche_profil_renvoie_les_infos_academiques(self):
        self._connecter("0341000002")
        reponse = self.client.get(f"/cercles/{self.cercle_id}/membres/{self.sarah_id}/profil")
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.json()
        self.assertEqual(corps["nom"], "Sarah")
        self.assertTrue(corps["photo"])
        self.assertEqual(corps["universite"], "Universite de Toamasina")
        self.assertEqual(corps["mention"], "Informatique")
        self.assertEqual(corps["filiere"], "Developpement Web")
        self.assertEqual(corps["niveau"], "L2")
        self.assertFalse(corps["est_moi"])

    def test_fiche_profil_champs_academiques_vides_quand_non_renseignes(self):
        self._connecter("0341000001")
        reponse = self.client.get(f"/cercles/{self.cercle_id}/membres/{self.thomas_id}/profil")
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.json()
        self.assertIsNone(corps["universite"])
        self.assertIsNone(corps["filiere"])
        self.assertIsNone(corps["niveau"])

    def test_fiche_profil_refusee_a_un_non_membre_du_cercle(self):
        self._connecter("0341000003")  # Elodie, pas membre de ce cercle
        reponse = self.client.get(f"/cercles/{self.cercle_id}/membres/{self.sarah_id}/profil")
        self.assertEqual(reponse.status_code, 403)

    def test_fiche_profil_dune_personne_hors_cercle_est_introuvable(self):
        self._connecter("0341000001")  # Sarah, membre du cercle
        reponse = self.client.get(f"/cercles/{self.cercle_id}/membres/{self.exterieur_id}/profil")
        self.assertEqual(reponse.status_code, 404)

    def test_fiche_profil_non_connecte_refusee(self):
        reponse = self.client.get(f"/cercles/{self.cercle_id}/membres/{self.sarah_id}/profil")
        self.assertEqual(reponse.status_code, 401)


if __name__ == "__main__":
    unittest.main()
