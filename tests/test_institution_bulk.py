import pytest

from app.routers.institution_router import (
    identifiant_etudiant,
    lire_lignes_tableur,
    normaliser_code_institution,
    normaliser_matricule,
)


def test_normaliser_code_etablissement():
    assert normaliser_code_institution("Université Toamasina") == "UNIVERSITE-TOAMASINA"


def test_code_etablissement_invalide():
    with pytest.raises(ValueError):
        normaliser_code_institution("!")


def test_matricule_conserve_les_zeros_initiaux():
    assert normaliser_matricule(" 001/2026 ") == "001/2026"


def test_identifiant_etudiant_est_deterministe():
    assert identifiant_etudiant("UNIV-T", "001/2026") == "UNIV-T-001-2026"


def test_lire_csv_point_virgule_et_entetes_compatibles():
    contenu = "nom;prenom;matricule;classe\nRakoto;Miora;001;L1\n"
    lignes = lire_lignes_tableur("etudiants.csv", contenu.encode("utf-8"))
    assert lignes == [{
        "ligne": "2",
        "nom": "Rakoto Miora",
        "matricule": "001",
        "telephone": "",
        "email": "",
        "niveau": "L1",
    }]


def test_lire_csv_refuse_entete_matricule_absente():
    with pytest.raises(ValueError, match="matricule"):
        lire_lignes_tableur("etudiants.csv", b"nom;classe\nRakoto;L1\n")


def test_lire_csv_refuse_format_non_pris_en_charge():
    with pytest.raises(ValueError, match="Format non pris en charge"):
        lire_lignes_tableur("etudiants.pdf", b"nom,matricule\na,1")


def test_lire_csv_refuse_plus_de_500_etudiants():
    lignes = ["nom;matricule"] + [f"Etudiant {i};{i}" for i in range(501)]
    with pytest.raises(ValueError, match="500 étudiants"):
        lire_lignes_tableur("etudiants.csv", "\n".join(lignes).encode("utf-8"))


def test_lire_xlsx():
    from io import BytesIO
    from openpyxl import Workbook

    classeur = Workbook()
    feuille = classeur.active
    feuille.append(["Nom", "Matricule", "Niveau"])
    feuille.append(["Rasoanaivo Miora", "0007", "L1"])
    contenu = BytesIO()
    classeur.save(contenu)
    classeur.close()
    lignes = lire_lignes_tableur("etudiants.xlsx", contenu.getvalue())
    assert lignes[0]["nom"] == "Rasoanaivo Miora"
    assert lignes[0]["matricule"] == "0007"
    assert lignes[0]["niveau"] == "L1"


def test_recuperation_mot_de_passe_accepte_un_identifiant_institutionnel(monkeypatch):
    from types import SimpleNamespace
    from app.routers import auth_router

    utilisateur = SimpleNamespace(
        id=777,
        telephone=None,
        identifiant_connexion="UNIV-T-001",
        email="eleve@example.test",
    )

    class Resultat:
        def first(self):
            return utilisateur

    class FausseSession:
        def __init__(self):
            self.requetes = 0
            self.ajouts = []
            self.commits = 0

        def exec(self, _requete):
            self.requetes += 1
            return Resultat()

        def add(self, objet):
            self.ajouts.append(objet)

        def commit(self):
            self.commits += 1

    request = SimpleNamespace(
        session={},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    session = FausseSession()
    emails = []
    monkeypatch.setattr(auth_router, "_ip_client", lambda _request: "127.0.0.1")
    monkeypatch.setattr(auth_router, "limite_depassee", lambda *args, **kwargs: False)
    monkeypatch.setattr(auth_router, "email_configure", lambda: True)
    monkeypatch.setattr(auth_router, "envoyer_email", lambda *args: emails.append(args))
    monkeypatch.setattr(auth_router, "hacher_mot_de_passe", lambda value: "hash:" + value)

    response = auth_router.demander_reinitialisation(
        request, "UNIV-T-001", session, None
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/mot-de-passe-oublie/code"
    assert request.session["en_attente_reinit_user_id"] == utilisateur.id
    assert session.requetes == 1
    assert session.commits == 1
    assert len(emails) == 1
    assert session.ajouts[0].utilisateur_id == utilisateur.id


def test_recuperation_mot_de_passe_limitee_ne_consulte_pas_la_base(monkeypatch):
    from types import SimpleNamespace
    from app.routers import auth_router

    class FausseSession:
        def exec(self, _requete):
            raise AssertionError("La base ne doit pas être interrogée après la limite anti-abus.")

    request = SimpleNamespace(
        session={},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    monkeypatch.setattr(auth_router, "_ip_client", lambda _request: "127.0.0.1")
    monkeypatch.setattr(auth_router, "limite_depassee", lambda *args, **kwargs: True)

    response = auth_router.demander_reinitialisation(
        request, "UNIV-T-001", FausseSession(), None
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/mot-de-passe-oublie/code"
    assert "en_attente_reinit_user_id" not in request.session


def test_etablissementpartenaire_indexe_le_createur():
    from app.models import EtablissementPartenaire

    indexes = {index.name for index in EtablissementPartenaire.__table__.indexes}
    assert "ix_etablissementpartenaire_cree_par_id" in indexes
