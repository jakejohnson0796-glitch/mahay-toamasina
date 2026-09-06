"""
Tests des routes de moderation de la classe virtuelle
(/classe/seances/{id}/salle/muter/{utilisateur_id} et .../expulser/{...}) :
verifie la frontiere de permission (seul le professeur DU cours concerne,
ou un admin, peut les appeler) et le garde-fou anti-auto-expulsion. Le
chemin "succes reel" (LiveKit repond, participant effectivement coupe)
n'est pas teste ici -- il exigerait un vrai serveur LiveKit ou un mock
du module livekit.api ; ce fichier verifie la logique d'autorisation cote
application, qui est ce qui protege des appels non voulus.

Lancer avec :
    python -m unittest tests.test_moderation_salle -v
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
from app import rate_limit  # noqa: E402
from app.models import Utilisateur, RoleUtilisateur, Cours, Seance, StatutSeance  # noqa: E402


def _connecter(client, telephone, mot_de_passe):
    page = client.get("/connexion")
    jeton = re.search(r'name="_csrf" value="([^"]+)"', page.text).group(1)
    reponse = client.post(
        "/connexion",
        data={"telephone": telephone, "mot_de_passe": mot_de_passe, "_csrf": jeton},
        follow_redirects=False,
    )
    assert reponse.status_code in (302, 303), reponse.text
    # Le jeton CSRF est stocke en session (voir app/csrf.py), pas
    # regenere par requete : celui obtenu avant la connexion reste valide
    # apres (meme session/cookie), pas besoin d'en relire un nouveau sur
    # une page post-connexion.
    return jeton


class TestModerationSalle(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        SQLModel.metadata.create_all(engine)

    def setUp(self):
        rate_limit._tentatives.clear()
        with Session(engine) as session:
            for table in (Seance, Cours, Utilisateur):
                for ligne in session.exec(select(table)).all():
                    session.delete(ligne)
            session.commit()

            prof = Utilisateur(nom="Prof Rakoto", telephone="0341100001", mot_de_passe_hash=hacher_mot_de_passe("MotDePasse123!"), role=RoleUtilisateur.PROFESSEUR)
            autre_prof = Utilisateur(nom="Prof Rasoa", telephone="0341100002", mot_de_passe_hash=hacher_mot_de_passe("MotDePasse123!"), role=RoleUtilisateur.PROFESSEUR)
            etudiant = Utilisateur(nom="Etudiant Jean", telephone="0341100003", mot_de_passe_hash=hacher_mot_de_passe("MotDePasse123!"), role=RoleUtilisateur.ETUDIANT)
            session.add_all([prof, autre_prof, etudiant])
            session.commit()
            for u in (prof, autre_prof, etudiant):
                session.refresh(u)
            # Ids captures en simples entiers : les objets ORM eux-memes
            # deviennent "detached" a la sortie du bloc "with Session"
            # ci-dessus, y accerder plus tard (dans les methodes de test)
            # leverait DetachedInstanceError des qu'un attribut non deja
            # charge est lu.
            self.prof_id = prof.id
            self.autre_prof_id = autre_prof.id
            self.etudiant_id = etudiant.id

            cours = Cours(nom="Comptabilite generale", matiere="Comptabilite", niveau="L2", professeur_id=prof.id)
            session.add(cours)
            session.commit()
            session.refresh(cours)
            self.cours_id = cours.id

            seance = Seance(cours_id=cours.id, titre="Seance 1", statut=StatutSeance.EN_COURS, nom_salle_livekit="salle-test-1")
            session.add(seance)
            session.commit()
            session.refresh(seance)
            self.seance_id = seance.id

    def test_non_connecte_refuse(self):
        client = TestClient(app)
        page = client.get("/connexion")
        jeton = re.search(r'name="_csrf" value="([^"]+)"', page.text).group(1)
        reponse = client.post(
            f"/classe/seances/{self.seance_id}/salle/muter/{self.etudiant_id}",
            data={"_csrf": jeton},
        )
        self.assertEqual(reponse.status_code, 401)

    def test_etudiant_ne_peut_pas_moderer(self):
        client = TestClient(app)
        jeton = _connecter(client, "0341100003", "MotDePasse123!")
        reponse = client.post(
            f"/classe/seances/{self.seance_id}/salle/muter/{self.prof_id}",
            data={"_csrf": jeton},
        )
        self.assertEqual(reponse.status_code, 403)

    def test_professeur_dun_autre_cours_ne_peut_pas_moderer(self):
        client = TestClient(app)
        jeton = _connecter(client, "0341100002", "MotDePasse123!")
        reponse = client.post(
            f"/classe/seances/{self.seance_id}/salle/expulser/{self.etudiant_id}",
            data={"_csrf": jeton},
        )
        self.assertEqual(reponse.status_code, 403)

    def test_professeur_du_cours_peut_appeler_la_route(self):
        # LiveKit n'est pas configure dans l'environnement de test : on
        # verifie que l'autorisation passe (503 "LiveKit non configure",
        # pas 403) plutot que le succes du mute lui-meme.
        client = TestClient(app)
        jeton = _connecter(client, "0341100001", "MotDePasse123!")
        reponse = client.post(
            f"/classe/seances/{self.seance_id}/salle/muter/{self.etudiant_id}",
            data={"_csrf": jeton},
        )
        self.assertEqual(reponse.status_code, 503)

    def test_professeur_ne_peut_pas_sexpulser_lui_meme(self):
        client = TestClient(app)
        jeton = _connecter(client, "0341100001", "MotDePasse123!")
        reponse = client.post(
            f"/classe/seances/{self.seance_id}/salle/expulser/{self.prof_id}",
            data={"_csrf": jeton},
        )
        self.assertEqual(reponse.status_code, 400)

    def test_admin_peut_moderer_nimporte_quel_cours(self):
        with Session(engine) as session:
            admin = Utilisateur(nom="Admin", telephone="0341100009", mot_de_passe_hash=hacher_mot_de_passe("MotDePasse123!"), role=RoleUtilisateur.ADMIN)
            session.add(admin)
            session.commit()
        client = TestClient(app)
        jeton = _connecter(client, "0341100009", "MotDePasse123!")
        reponse = client.post(
            f"/classe/seances/{self.seance_id}/salle/muter/{self.etudiant_id}",
            data={"_csrf": jeton},
        )
        self.assertEqual(reponse.status_code, 503)  # autorise, bloque seulement par LiveKit non configure


if __name__ == "__main__":
    unittest.main()
