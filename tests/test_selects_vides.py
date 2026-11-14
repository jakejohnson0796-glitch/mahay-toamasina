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
    ReferentielScolaire, NiveauScolaire, Abonnement, AbonnementEtudiant,
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
                mot_de_passe_hash=hacher_mot_de_passe("MotDePasse123!"),
                mot_de_passe_confirmation_admin_hash=hacher_mot_de_passe("ConfirmationAdmin123!"),
                role=RoleUtilisateur.ADMIN,
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

    def test_profil_academique_charge_apres_connexion(self):
        client = TestClient(app)
        _connecter(client, "0340000002")
        page = client.get("/profil/academique")
        self.assertEqual(page.status_code, 200, page.text[:300])

    # --- Interface inscription : la cascade JS doit etre initialisee ---
    def test_inscription_charge_la_cascade_academique(self):
        client = TestClient(app)
        page = client.get("/inscription")
        self.assertEqual(page.status_code, 200)
        self.assertIn('data-cascade-academique', page.text)
        self.assertIn('static/js/cascade-academique.js', page.text)
        self.assertIn('id="universite_id"', page.text)
        self.assertIn('id="composante_id"', page.text)
        self.assertIn('id="mention_id"', page.text)
        self.assertIn('id="niveau"', page.text)
        self.assertIn('id="filiere_id"', page.text)

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
                "accepter_conditions": "oui",
                "_csrf": jeton,
            },
            follow_redirects=False,
        )
        # Le parser doit accepter les selects vides sans 422, puis la
        # validation metier refuse correctement un profil etudiant incomplet.
        self.assertEqual(reponse.status_code, 200, reponse.text[:300])
        with Session(engine) as session:
            from sqlmodel import select
            u = session.exec(select(Utilisateur).where(Utilisateur.telephone == "0340000099")).first()
            self.assertIsNone(u)


    def _inscrire_profil(
        self, telephone, *, role="etudiant", responsable=False,
        cycle=None, niveau_scolaire_id=None
    ):
        client = TestClient(app)
        jeton = _jeton_csrf(client, "/inscription")
        donnees = {
            "nom": f"Compte {telephone}",
            "telephone": telephone,
            "mot_de_passe": "MotDePasse123!",
            "role": role,
            "accepter_conditions": "oui",
            "_csrf": jeton,
        }
        if responsable:
            donnees["mode_responsable"] = "oui"
        if cycle:
            donnees["cycle_education"] = cycle
        if niveau_scolaire_id is not None:
            donnees["niveau_scolaire_id"] = str(niveau_scolaire_id)
        response = client.post("/inscription", data=donnees, follow_redirects=False)
        return client, response

    def test_inscription_sponsor_attend_validation_et_ne_peut_pas_ouvrir_dashboard(self):
        client, response = self._inscrire_profil("0340000111", role="sponsor")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/demande-validation")

        with Session(engine) as session:
            from sqlmodel import select
            user = session.exec(select(Utilisateur).where(Utilisateur.telephone == "0340000111")).first()
            self.assertIsNotNone(user)
            self.assertEqual(user.role, RoleUtilisateur.ETUDIANT)
            self.assertEqual(user.profil_souhaite, "sponsor")
            self.assertEqual(user.statut_verification_sponsor, "en_attente")
            self.assertIsNone(
                session.exec(select(Abonnement).where(Abonnement.utilisateur_id == user.id)).first()
            )

        page = client.get("/demande-validation")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Sponsor", page.text)
        dashboard = client.get("/dashboard", follow_redirects=False)
        self.assertEqual(dashboard.status_code, 303)
        self.assertEqual(dashboard.headers["location"], "/demande-validation")

    def test_inscription_responsable_attend_validation_et_n_ouvre_pas_espace_famille(self):
        client, response = self._inscrire_profil("0340000112", responsable=True)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/demande-validation")

        with Session(engine) as session:
            from sqlmodel import select
            user = session.exec(select(Utilisateur).where(Utilisateur.telephone == "0340000112")).first()
            self.assertIsNotNone(user)
            self.assertEqual(user.role, RoleUtilisateur.ETUDIANT)
            self.assertEqual(user.profil_souhaite, "responsable")
            self.assertEqual(user.statut_verification_responsable, "en_attente")

        page = client.get("/demande-validation")
        self.assertEqual(page.status_code, 200)
        self.assertIn("responsable légal", page.text.lower())
        famille = client.get("/famille", follow_redirects=False)
        self.assertEqual(famille.status_code, 303)
        self.assertEqual(famille.headers["location"], "/demande-validation")

    def test_inscription_enseignant_et_repetiteur_cree_des_demandes_non_actives(self):
        with Session(engine) as session:
            referentiel = ReferentielScolaire(
                code="MEN-TEST-INSCRIPTION-ENSEIGNANT",
                libelle="Référentiel test inscription enseignant",
                source_officielle="https://www.education.gov.mg/",
                statut="partiel",
            )
            session.add(referentiel)
            session.commit()
            session.refresh(referentiel)
            niveau = NiveauScolaire(
                referentiel_id=referentiel.id,
                code="5E_TEST",
                libelle="5e test",
                cycle="college",
                ordre=2,
                est_active=True,
                source_officielle=referentiel.source_officielle,
                statut_validation="verifie",
            )
            session.add(niveau)
            session.commit()
            session.refresh(niveau)
            niveau_id = niveau.id

        client_prof, response_prof = self._inscrire_profil(
            "0340000113",
            role="professeur",
            cycle="college",
            niveau_scolaire_id=niveau_id,
        )
        self.assertEqual(response_prof.status_code, 303)
        self.assertEqual(response_prof.headers["location"], "/demande-validation")
        client_rep, response_rep = self._inscrire_profil(
            "0340000114", role="repetiteur"
        )
        self.assertEqual(response_rep.status_code, 303)
        self.assertEqual(response_rep.headers["location"], "/demande-validation")

        with Session(engine) as session:
            from sqlmodel import select
            prof = session.exec(select(Utilisateur).where(Utilisateur.telephone == "0340000113")).first()
            rep = session.exec(select(Utilisateur).where(Utilisateur.telephone == "0340000114")).first()
            self.assertEqual(prof.role, RoleUtilisateur.ETUDIANT)
            self.assertEqual(prof.statut_verification_enseignant, "en_attente")
            self.assertEqual(rep.role, RoleUtilisateur.ETUDIANT)
            self.assertEqual(rep.statut_verification_repetiteur, "en_attente")

        self.assertEqual(client_prof.get("/dashboard", follow_redirects=False).headers["location"], "/demande-validation")
        self.assertEqual(client_rep.get("/dashboard", follow_redirects=False).headers["location"], "/demande-validation")

    def test_inscription_eleve_conserve_activation_directe(self):
        with Session(engine) as session:
            referentiel = ReferentielScolaire(
                code="MEN-TEST-INSCRIPTION-DIRECTE",
                libelle="Référentiel test inscription directe",
                source_officielle="https://www.education.gov.mg/",
                statut="partiel",
            )
            session.add(referentiel)
            session.commit()
            session.refresh(referentiel)
            niveau = NiveauScolaire(
                referentiel_id=referentiel.id,
                code="6E_TEST",
                libelle="6e test",
                cycle="college",
                ordre=1,
                est_active=True,
                source_officielle=referentiel.source_officielle,
                statut_validation="verifie",
            )
            session.add(niveau)
            session.commit()
            session.refresh(niveau)
            niveau_id = niveau.id

        client, response = self._inscrire_profil(
            "0340000115",
            role="etudiant",
            cycle="college",
            niveau_scolaire_id=niveau_id,
        )
        self.assertEqual(response.status_code, 303, response.text[:300])
        self.assertEqual(response.headers["location"], "/bienvenue")
        with Session(engine) as session:
            from sqlmodel import select
            user = session.exec(select(Utilisateur).where(Utilisateur.telephone == "0340000115")).first()
            self.assertIsNotNone(user)
            self.assertEqual(user.role, RoleUtilisateur.ETUDIANT)
            self.assertEqual(user.profil_souhaite, "eleve")
            self.assertEqual(user.statut_verification_enseignant, "non_concerne")
            self.assertIsNotNone(
                session.exec(
                    select(AbonnementEtudiant).where(
                        AbonnementEtudiant.utilisateur_id == user.id
                    )
                ).first()
            )


    # --- 5. POST /admin/referentiel/filieres/{id}/assigner-mention avec mention_id="" ---
    def test_assigner_mention_vide_retire_la_mention(self):
        client = TestClient(app)
        _connecter(client, "0340000001")
        jeton = _jeton_csrf(client, "/admin/referentiel")
        reponse = client.post(
            f"/admin/referentiel/filieres/{self.filiere_id}/assigner-mention",
            data={
                "mention_id": "",
                "admin_confirmation_password": "ConfirmationAdmin123!",
                "_csrf": jeton,
            },
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
            data={
                "mention_id": "",
                "niveau": "",
                "admin_confirmation_password": "ConfirmationAdmin123!",
                "_csrf": jeton,
            },
            follow_redirects=False,
        )
        self.assertEqual(reponse.status_code, 303, reponse.text[:300])


if __name__ == "__main__":
    unittest.main()
