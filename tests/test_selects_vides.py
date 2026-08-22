"""
Reproduit et verifie la correction du bug rapporte : choisir l'option
vide d'un <select> ("Toutes les filieres", "— aucune —", etc.) faisait
planter la route avec une erreur 422 brute (Pydantic essayait de parser
"" comme un entier AVANT que le corps de la fonction ne s'execute).

Couvre les 6 endroits ou ce motif existait :
1. GET  /cercles                                  (filiere_id)
2. GET  /documents                                 (filiere_id)
3. POST /cercles/creer                             (filiere_id, "groupe libre")
4. POST /inscription                               (filiere_id, universite_id)
5. POST /admin/referentiel/filieres/{id}/assigner-mention  (mention_id)
6. POST /admin/referentiel/cercles/{id}/assigner   (mention_id)

Lancer avec :
    python -m unittest tests.test_selects_vides -v
"""
import os
import re
import unittest
import tempfile

_DB_FICHIER = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FICHIER}"
os.environ.setdefault("SESSION_SECRET_KEY", "cle-de-test-uniquement-jamais-en-production")

from starlette.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app.main import app  # noqa: E402
from app.database import engine  # noqa: E402
from app.auth import hacher_mot_de_passe  # noqa: E402
from app.models import (  # noqa: E402
    Utilisateur, RoleUtilisateur, Universite, Faculte, Mention, Filiere, CercleEtude,
)


def _jeton_csrf(client: TestClient, url_page_avec_form: str) -> str:
    page = client.get(url_page_avec_form)
    return re.search(r'name="_csrf" value="([^"]+)"', page.text).group(1)


def _connecter(client: TestClient, telephone: str, mot_de_passe: str = "MotDePasse123!") -> None:
    jeton = _jeton_csrf(client, "/connexion")
    reponse = client.post(
        "/connexion",
        data={"telephone": telephone, "mot_de_passe": mot_de_passe, "_csrf": jeton},
        follow_redirects=False,
    )
    assert reponse.status_code == 303, f"Echec connexion: {reponse.status_code} {reponse.text[:200]}"


class TestSelectsVides(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with TestClient(app):
            pass  # declenche l'evenement startup (migrations + tables)

        with Session(engine) as session:
            universite = Universite(nom="Universite de Test Selects Vides")
            session.add(universite); session.commit(); session.refresh(universite)
            faculte = Faculte(nom="DEGMIA", universite_id=universite.id)
            session.add(faculte); session.commit(); session.refresh(faculte)
            mention = Mention(nom="Sciences de Gestion (test selects)")
            session.add(mention); session.commit(); session.refresh(mention)
            filiere = Filiere(nom="Finance (test selects)", faculte_id=faculte.id, mention_id=mention.id)
            session.add(filiere); session.commit(); session.refresh(filiere)
            cls.mention_id = mention.id
            cls.filiere_id = filiere.id

            admin = Utilisateur(
                nom="Admin Test", telephone="0340000001",
                mot_de_passe_hash=hacher_mot_de_passe("MotDePasse123!"), role=RoleUtilisateur.ADMIN,
            )
            session.add(admin); session.commit(); session.refresh(admin)
            cls.admin_id = admin.id

            etudiant = Utilisateur(
                nom="Etudiant Test", telephone="0340000002",
                mot_de_passe_hash=hacher_mot_de_passe("MotDePasse123!"), role=RoleUtilisateur.ETUDIANT,
            )
            session.add(etudiant); session.commit(); session.refresh(etudiant)

            cercle = CercleEtude(nom="Cercle test assignation", createur_id=etudiant.id)
            session.add(cercle); session.commit(); session.refresh(cercle)
            cls.cercle_id = cercle.id

    # --- 1. GET /cercles?filiere_id= ---
    def test_liste_cercles_filiere_id_vide(self):
        client = TestClient(app)
        page = client.get("/cercles", params={"filiere_id": ""})
        self.assertEqual(page.status_code, 200)

    # --- 2. GET /documents?filiere_id= ---
    def test_liste_documents_filiere_id_vide(self):
        client = TestClient(app)
        page = client.get("/documents", params={"filiere_id": ""})
        self.assertEqual(page.status_code, 200)

    # --- 3. POST /cercles/creer avec filiere_id="" ("groupe libre") ---
    def test_creer_cercle_groupe_libre_filiere_id_vide(self):
        client = TestClient(app)
        _connecter(client, "0340000002")
        jeton = _jeton_csrf(client, "/cercles")
        reponse = client.post(
            "/cercles/creer",
            data={"nom": "Groupe libre test", "filiere_id": "", "niveau": "", "_csrf": jeton},
            follow_redirects=False,
        )
        self.assertEqual(reponse.status_code, 303, reponse.text[:300])
        self.assertNotIn("erreur", reponse.headers.get("location", ""))

    # --- 4. POST /inscription avec filiere_id="" et universite_id="" ---
    def test_inscription_sans_filiere_ni_universite(self):
        client = TestClient(app)
        jeton = _jeton_csrf(client, "/inscription")
        reponse = client.post(
            "/inscription",
            data={
                "nom": "Nouvel Etudiant", "telephone": "0340000099",
                "mot_de_passe": "MotDePasse123!",
                "filiere_id": "", "universite_id": "",
                "_csrf": jeton,
            },
            follow_redirects=False,
        )
        self.assertEqual(reponse.status_code, 303, reponse.text[:300])
        with Session(engine) as session:
            from sqlmodel import select
            u = session.exec(select(Utilisateur).where(Utilisateur.telephone == "0340000099")).first()
            self.assertIsNotNone(u)
            self.assertIsNone(u.filiere_id)
            self.assertIsNone(u.universite_id)

    # --- 5. POST /admin/referentiel/filieres/{id}/assigner-mention avec mention_id="" ---
    def test_assigner_mention_vide_retire_la_mention(self):
        client = TestClient(app)
        _connecter(client, "0340000001")
        jeton = _jeton_csrf(client, "/admin/referentiel")
        reponse = client.post(
            f"/admin/referentiel/filieres/{self.filiere_id}/assigner-mention",
            data={"mention_id": "", "_csrf": jeton},
            follow_redirects=False,
        )
        self.assertEqual(reponse.status_code, 303, reponse.text[:300])
        with Session(engine) as session:
            filiere = session.get(Filiere, self.filiere_id)
            self.assertIsNone(filiere.mention_id)
            # remise en place pour ne pas perturber d'eventuels tests suivants
            filiere.mention_id = self.mention_id
            session.add(filiere); session.commit()

    # --- 6. POST /admin/referentiel/cercles/{id}/assigner avec mention_id="" ---
    def test_assigner_cercle_mention_vide(self):
        client = TestClient(app)
        _connecter(client, "0340000001")
        jeton = _jeton_csrf(client, "/admin/referentiel/cercles")
        reponse = client.post(
            f"/admin/referentiel/cercles/{self.cercle_id}/assigner",
            data={"mention_id": "", "niveau": "", "_csrf": jeton},
            follow_redirects=False,
        )
        self.assertEqual(reponse.status_code, 303, reponse.text[:300])


if __name__ == "__main__":
    unittest.main()
