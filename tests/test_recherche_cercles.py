"""
Test d'integration HTTP (bout en bout, via TestClient) pour la barre de
recherche/filtres de GET /cercles : nom (q), filiere, niveau, et la case
"disponibles pour moi".

Meme approche que test_messagerie_enrichie.py : vraies routes HTTP, vrai
login, pour valider la route ET le template ensemble (pas seulement
condition_cercles_disponibles(), deja teste isolement dans
test_referentiel_academique.py).

Lancer avec :
    python -m unittest tests.test_recherche_cercles -v
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
from sqlmodel import Session  # noqa: E402

from app.main import app  # noqa: E402
from app.database import engine  # noqa: E402
from app.auth import hacher_mot_de_passe  # noqa: E402
from app.models import (  # noqa: E402
    Utilisateur, RoleUtilisateur, CercleEtude, Universite, Faculte, Mention, Filiere,
)


def _creer_client_connecte(telephone: str, nom: str, **champs_utilisateur) -> TestClient:
    with Session(engine) as session:
        utilisateur = Utilisateur(
            nom=nom, telephone=telephone,
            mot_de_passe_hash=hacher_mot_de_passe("MotDePasse123!"),
            role=RoleUtilisateur.ETUDIANT,
            **champs_utilisateur,
        )
        session.add(utilisateur)
        session.commit()

    client = TestClient(app)
    page = client.get("/connexion")
    jeton = re.search(r'name="_csrf" value="([^"]+)"', page.text).group(1)
    reponse = client.post(
        "/connexion",
        data={"telephone": telephone, "mot_de_passe": "MotDePasse123!", "_csrf": jeton},
        follow_redirects=False,
    )
    assert reponse.status_code == 303, f"Echec connexion: {reponse.status_code} {reponse.text[:200]}"
    return client


class TestRechercheCercles(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with TestClient(app):
            pass  # declenche l'evenement startup (migrations + tables)

        with Session(engine) as session:
            universite = Universite(nom="Universite de Test Recherche Cercles")
            session.add(universite); session.commit(); session.refresh(universite)
            faculte = Faculte(nom="DEGMIA", universite_id=universite.id)
            session.add(faculte); session.commit(); session.refresh(faculte)
            mention = Mention(nom="Sciences de Gestion")
            session.add(mention); session.commit(); session.refresh(mention)
            filiere = Filiere(nom="Finance et Comptabilite", faculte_id=faculte.id, mention_id=mention.id)
            session.add(filiere); session.commit(); session.refresh(filiere)
            cls.filiere_id = filiere.id
            autre_filiere = Filiere(nom="Droit prive", faculte_id=faculte.id, mention_id=mention.id)
            session.add(autre_filiere); session.commit(); session.refresh(autre_filiere)
            cls.autre_filiere_id = autre_filiere.id

            createur = Utilisateur(nom="Createur", telephone="0350000001", mot_de_passe_hash="x", role=RoleUtilisateur.ETUDIANT)
            session.add(createur); session.commit(); session.refresh(createur)
            createur_id = createur.id

            session.add(CercleEtude(nom="Revision Analyse Financiere", createur_id=createur_id))
            session.add(CercleEtude(
                nom="Finance et Comptabilite — Licence 3", createur_id=createur_id,
                mention_id=mention.id, filiere_id=filiere.id, niveau="L3",
            ))
            session.add(CercleEtude(
                nom="Droit prive — Licence 3", createur_id=createur_id,
                mention_id=mention.id, filiere_id=autre_filiere.id, niveau="L3",
            ))
            session.commit()

        cls.client = _creer_client_connecte("0350000099", "Etudiant Test", filiere_id=cls.filiere_id, niveau="L3")

    def test_sans_filtre_affiche_tous_les_cercles(self):
        page = self.client.get("/cercles")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Revision Analyse Financiere", page.text)
        self.assertIn("Finance et Comptabilite — Licence 3", page.text)
        self.assertIn("Droit prive — Licence 3", page.text)

    def test_recherche_par_nom_filtre_correctement(self):
        page = self.client.get("/cercles", params={"q": "Analyse Financiere"})
        self.assertEqual(page.status_code, 200)
        self.assertIn("Revision Analyse Financiere", page.text)
        self.assertNotIn("Finance et Comptabilite — Licence 3", page.text)
        self.assertNotIn("Droit prive — Licence 3", page.text)

    def test_recherche_par_nom_insensible_a_la_casse(self):
        page = self.client.get("/cercles", params={"q": "analyse financiere"})
        self.assertIn("Revision Analyse Financiere", page.text)

    def test_filtre_par_filiere(self):
        page = self.client.get("/cercles", params={"filiere_id": str(self.autre_filiere_id)})
        self.assertIn("Droit prive — Licence 3", page.text)
        self.assertNotIn("Finance et Comptabilite — Licence 3", page.text)

    def test_filtre_par_niveau_invalide_est_ignore_silencieusement(self):
        """Un niveau bricole dans l'URL ne doit pas planter la page — le
        filtre est simplement ignore (voir liste_cercles)."""
        page = self.client.get("/cercles", params={"niveau": "NIVEAU_INEXISTANT"})
        self.assertEqual(page.status_code, 200)
        self.assertIn("Revision Analyse Financiere", page.text)

    def test_disponibles_pour_moi_exclut_le_cercle_national_dune_autre_filiere(self):
        """L'etudiant de test est en Finance L3 : il doit voir le cercle
        libre + son propre cercle national, mais pas celui de Droit."""
        page = self.client.get("/cercles", params={"disponibles": "1"})
        self.assertIn("Revision Analyse Financiere", page.text)
        self.assertIn("Finance et Comptabilite — Licence 3", page.text)
        self.assertNotIn("Droit prive — Licence 3", page.text)

    def test_recherche_vide_ne_correspond_a_rien_affiche_etat_vide(self):
        page = self.client.get("/cercles", params={"q": "xyzxyzxyz-introuvable"})
        self.assertIn("Aucun resultat", page.text)


if __name__ == "__main__":
    unittest.main()
