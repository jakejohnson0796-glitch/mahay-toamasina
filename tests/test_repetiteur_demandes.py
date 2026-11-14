from types import SimpleNamespace

from fastapi.responses import RedirectResponse

from app.models import DemandeAccompagnement, RoleUtilisateur
from app.routers import repetiteur_router


class _Resultat:
    def __init__(self, valeurs=None):
        self.valeurs = list(valeurs or [])

    def all(self):
        return self.valeurs

    def first(self):
        return self.valeurs[0] if self.valeurs else None


class _SessionFausse:
    def __init__(self, cible=None, resultats=None):
        self.cible = cible
        self.resultats = list(resultats or [])
        self.ajoutes = []
        self.supprimes = []
        self.commits = 0

    def get(self, _modele, _identifiant):
        return self.cible

    def exec(self, _requete):
        if self.resultats:
            return self.resultats.pop(0)
        return _Resultat()

    def add(self, objet):
        self.ajoutes.append(objet)

    def delete(self, objet):
        self.supprimes.append(objet)

    def commit(self):
        self.commits += 1


def _eleve():
    return SimpleNamespace(
        id=11,
        nom="Élève Exemple",
        role=RoleUtilisateur.ETUDIANT,
        banni=False,
    )


def _repetiteur():
    return SimpleNamespace(
        id=22,
        nom="Répétiteur Vérifié",
        role=RoleUtilisateur.REPETITEUR,
        banni=False,
        statut_verification_repetiteur="approuve",
        telephone="0341234567",
        email="prive@example.mg",
        matieres_repetiteur="Mathématiques, Physique",
        niveaux_repetiteur="Collège, Lycée",
        tarif_horaire_repetiteur_ariary=10000,
        bio="Accompagnement pédagogique.",
    )


def test_nom_public_repetiteur_ne_montre_que_le_prenom_et_l_initiale():
    assert repetiteur_router.nom_public_repetiteur("Rado Randriam") == "Rado R."


def test_projection_publique_ne_contient_aucune_coordonee_de_compte():
    profil = repetiteur_router._profil_public(_repetiteur())

    assert set(profil) == {"id", "nom", "matieres", "niveaux", "tarif", "presentation"}
    assert "telephone" not in profil
    assert "email" not in profil
    assert "0341234567" not in str(profil)
    assert "prive@example.mg" not in str(profil)



def test_un_compte_repetiteur_banni_est_considere_indisponible():
    repetiteur = _repetiteur()
    repetiteur.banni = True

    assert repetiteur_router._est_repetiteur_verifie(repetiteur) is False


def test_projection_publique_masque_les_coordonnees_ecrites_dans_la_bio():
    repetiteur = _repetiteur()
    repetiteur.bio = "Cours de maths, contacte-moi à prive@example.mg"

    profil = repetiteur_router._profil_public(repetiteur)

    assert "prive@example.mg" not in profil["presentation"]
    assert "masquée" in profil["presentation"]


def test_un_eleve_peut_envoyer_une_demande_a_un_repetiteur_verifie(monkeypatch):
    eleve = _eleve()
    repetiteur = _repetiteur()
    session = _SessionFausse(cible=repetiteur)
    monkeypatch.setattr(repetiteur_router, "utilisateur_courant", lambda *_args: eleve)

    reponse = repetiteur_router.creer_demande_accompagnement(
        SimpleNamespace(),
        repetiteur.id,
        "Mathématiques",
        "Terminale",
        "Je souhaite travailler les fonctions et les dérivées.",
        session,
        None,
    )

    assert isinstance(reponse, RedirectResponse)
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/mes-demandes-repetiteur?ok=demande_envoyee"
    assert session.commits == 1
    demande = session.ajoutes[0]
    assert isinstance(demande, DemandeAccompagnement)
    assert demande.etudiant_id == eleve.id
    assert demande.repetiteur_id == repetiteur.id
    assert demande.statut == "en_attente"
    assert not hasattr(demande, "telephone")
    assert not hasattr(demande, "email")


def test_une_demande_ne_peut_pas_contenir_un_numero_ou_un_lien(monkeypatch):
    eleve = _eleve()
    session = _SessionFausse(cible=_repetiteur())
    monkeypatch.setattr(repetiteur_router, "utilisateur_courant", lambda *_args: eleve)

    reponse = repetiteur_router.creer_demande_accompagnement(
        SimpleNamespace(),
        22,
        "Mathématiques",
        "Terminale",
        "Appelle-moi au 0341234567 pour les cours.",
        session,
        None,
    )

    assert isinstance(reponse, RedirectResponse)
    assert "coordonnees_interdites" in reponse.headers["location"]
    assert session.ajoutes == []
    assert session.commits == 0


def test_un_compte_non_eleve_ne_peut_pas_envoyer_de_demande(monkeypatch):
    sponsor = SimpleNamespace(id=4, role=RoleUtilisateur.SPONSOR)
    session = _SessionFausse(cible=_repetiteur())
    monkeypatch.setattr(repetiteur_router, "utilisateur_courant", lambda *_args: sponsor)

    reponse = repetiteur_router.creer_demande_accompagnement(
        SimpleNamespace(), 22, "Mathématiques", "Terminale",
        "Je souhaite travailler les fonctions.", session, None
    )

    assert isinstance(reponse, RedirectResponse)
    assert reponse.headers["location"] == "/dashboard"
    assert session.ajoutes == []
    assert session.commits == 0


def test_un_repetiteur_ne_peut_traiter_que_ses_propres_demandes(monkeypatch):
    repetiteur = _repetiteur()
    demande = SimpleNamespace(
        id=88,
        repetiteur_id=999,
        statut="en_attente",
        date_traitement=None,
    )
    session = _SessionFausse(cible=demande)
    monkeypatch.setattr(repetiteur_router, "utilisateur_courant", lambda *_args: repetiteur)

    reponse = repetiteur_router.traiter_demande_accompagnement(
        SimpleNamespace(), demande.id, "acceptee", session, None
    )

    assert isinstance(reponse, RedirectResponse)
    assert session.commits == 0
    assert demande.statut == "en_attente"


def test_repetiteur_verifie_peut_accepter_une_demande_adressee(monkeypatch):
    repetiteur = _repetiteur()
    demande = SimpleNamespace(
        id=88,
        repetiteur_id=repetiteur.id,
        statut="en_attente",
        date_traitement=None,
    )
    session = _SessionFausse(cible=demande)
    monkeypatch.setattr(repetiteur_router, "utilisateur_courant", lambda *_args: repetiteur)

    reponse = repetiteur_router.traiter_demande_accompagnement(
        SimpleNamespace(), demande.id, "acceptee", session, None
    )

    assert isinstance(reponse, RedirectResponse)
    assert reponse.headers["location"] == "/dashboard?ok=demande_acceptee#rep-demandes"
    assert demande.statut == "acceptee"
    assert demande.date_traitement is not None
    assert session.commits == 1


def test_un_repetiteur_non_valide_ne_peut_pas_accepter_une_demande(monkeypatch):
    repetiteur = _repetiteur()
    repetiteur.statut_verification_repetiteur = "retire"
    demande = SimpleNamespace(
        id=88,
        repetiteur_id=repetiteur.id,
        statut="en_attente",
        date_traitement=None,
    )
    session = _SessionFausse(cible=demande)
    monkeypatch.setattr(repetiteur_router, "utilisateur_courant", lambda *_args: repetiteur)

    repetiteur_router.traiter_demande_accompagnement(
        SimpleNamespace(), demande.id, "acceptee", session, None
    )

    assert demande.statut == "en_attente"
    assert session.commits == 0



def test_un_eleve_ne_peut_pas_envoyer_plus_de_cinq_demandes_en_attente(monkeypatch):
    eleve = _eleve()
    session = _SessionFausse(
        cible=_repetiteur(),
        resultats=[_Resultat([
            SimpleNamespace(repetiteur_id=31),
            SimpleNamespace(repetiteur_id=32),
            SimpleNamespace(repetiteur_id=33),
            SimpleNamespace(repetiteur_id=34),
            SimpleNamespace(repetiteur_id=35),
        ])],
    )
    monkeypatch.setattr(repetiteur_router, "utilisateur_courant", lambda *_args: eleve)

    reponse = repetiteur_router.creer_demande_accompagnement(
        SimpleNamespace(),
        22,
        "Mathématiques",
        "Terminale",
        "Je souhaite travailler les fonctions.",
        session,
        None,
    )

    assert isinstance(reponse, RedirectResponse)
    assert "limite_demandes" in reponse.headers["location"]
    assert session.ajoutes == []
    assert session.commits == 0


def test_l_annuaire_est_reserve_aux_eleves_connectes(monkeypatch):
    admin = SimpleNamespace(id=3, role=RoleUtilisateur.ADMIN)
    monkeypatch.setattr(repetiteur_router, "utilisateur_courant", lambda *_args: admin)
    session = _SessionFausse()

    reponse = repetiteur_router.annuaire_repetiteurs(SimpleNamespace(), None, session)

    assert isinstance(reponse, RedirectResponse)
    assert reponse.headers["location"] == "/dashboard"


def test_un_eleve_ne_peut_pas_utiliser_la_route_de_traitement_repetiteur(monkeypatch):
    eleve = _eleve()
    demande = SimpleNamespace(id=88, repetiteur_id=eleve.id, statut="en_attente")
    session = _SessionFausse(cible=demande)
    monkeypatch.setattr(repetiteur_router, "utilisateur_courant", lambda *_args: eleve)

    reponse = repetiteur_router.traiter_demande_accompagnement(
        SimpleNamespace(), demande.id, "acceptee", session, None
    )

    assert isinstance(reponse, RedirectResponse)
    assert reponse.headers["location"] == "/dashboard"
    assert session.commits == 0
