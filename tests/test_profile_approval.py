from pathlib import Path
from types import SimpleNamespace

from fastapi.responses import RedirectResponse

from app.models import RoleUtilisateur, Utilisateur
from app.profile_approval import details_validation_profil, profil_validation_requise
from app.routers import admin_router
from app.force_password_change import chemin_autorise_pendant_validation


class _SessionFausse:
    def __init__(self, cible):
        self.cible = cible
        self.ajoutes = []
        self.commits = 0

    def get(self, _modele, _identifiant):
        return self.cible

    def add(self, objet):
        self.ajoutes.append(objet)

    def commit(self):
        self.commits += 1


def _admin():
    return SimpleNamespace(id=7, role=RoleUtilisateur.ADMIN)


def _candidat(profil):
    return SimpleNamespace(
        id=21,
        nom="Compte candidat",
        banni=False,
        role=RoleUtilisateur.ETUDIANT,
        profil_souhaite=profil,
        statut_verification_sponsor="en_attente",
        statut_verification_responsable="en_attente",
        verification_sponsor_le=None,
        verification_responsable_le=None,
        verification_sponsor_par_id=None,
        verification_responsable_par_id=None,
        motif_refus_sponsor=None,
        motif_refus_responsable=None,
    )


def test_tout_profil_non_eleve_en_attente_ou_refuse_est_bloque():
    cas = [
        ("professeur", "statut_verification_enseignant"),
        ("repetiteur", "statut_verification_repetiteur"),
        ("sponsor", "statut_verification_sponsor"),
        ("responsable", "statut_verification_responsable"),
    ]
    for profil, champ in cas:
        candidat = SimpleNamespace(
            profil_souhaite=profil,
            **{champ: "en_attente"},
        )
        assert profil_validation_requise(candidat)
        assert details_validation_profil(candidat)["profil"] == profil
        setattr(candidat, champ, "refuse")
        assert profil_validation_requise(candidat)
        setattr(candidat, champ, "approuve")
        assert not profil_validation_requise(candidat)


def test_eleve_n_est_jamais_envoye_en_validation_non_eleve():
    eleve = SimpleNamespace(
        profil_souhaite="eleve",
        statut_verification_enseignant="non_concerne",
        statut_verification_repetiteur="non_concerne",
        statut_verification_sponsor="non_concerne",
        statut_verification_responsable="non_concerne",
    )
    assert not profil_validation_requise(eleve)
    assert details_validation_profil(eleve) is None


def test_middleware_autorise_suivi_et_securite_mais_pas_les_fonctionnalites():
    assert chemin_autorise_pendant_validation("GET", "/demande-validation")
    assert chemin_autorise_pendant_validation("GET", "/securite")
    assert chemin_autorise_pendant_validation("POST", "/securite/mot-de-passe")
    assert chemin_autorise_pendant_validation("POST", "/deconnexion")
    assert chemin_autorise_pendant_validation("GET", "/static/auth.css")
    assert not chemin_autorise_pendant_validation("GET", "/dashboard")
    assert not chemin_autorise_pendant_validation("GET", "/famille")
    assert not chemin_autorise_pendant_validation("POST", "/sponsoring/contact")
    assert not chemin_autorise_pendant_validation("POST", "/quiz/generer")


def test_admin_approuve_sponsor_seulement_si_demande_en_attente(monkeypatch):
    cible = _candidat("sponsor")
    session = _SessionFausse(cible)
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: _admin())

    response = admin_router.approuver_demande_sponsor(
        SimpleNamespace(), cible.id, session, None
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert cible.role == RoleUtilisateur.SPONSOR
    assert cible.statut_verification_sponsor == "approuve"
    assert cible.verification_sponsor_par_id == 7
    assert cible.verification_sponsor_le is not None
    assert session.commits == 1


def test_admin_refuse_sponsor_sans_lui_donner_les_droits(monkeypatch):
    cible = _candidat("sponsor")
    session = _SessionFausse(cible)
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: _admin())

    response = admin_router.refuser_demande_sponsor(
        SimpleNamespace(), cible.id, "Activité non vérifiée", session, None
    )

    assert isinstance(response, RedirectResponse)
    assert cible.role == RoleUtilisateur.ETUDIANT
    assert cible.statut_verification_sponsor == "refuse"
    assert cible.motif_refus_sponsor == "Activité non vérifiée"
    assert cible.verification_sponsor_par_id == 7
    assert session.commits == 1


def test_admin_approuve_responsable_sans_creer_automatiquement_de_lien_enfant(monkeypatch):
    cible = _candidat("responsable")
    session = _SessionFausse(cible)
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: _admin())

    response = admin_router.approuver_demande_responsable(
        SimpleNamespace(), cible.id, session, None
    )

    assert isinstance(response, RedirectResponse)
    assert cible.role == RoleUtilisateur.RESPONSABLE
    assert cible.statut_verification_responsable == "approuve"
    assert cible.verification_responsable_par_id == 7
    assert cible.verification_responsable_le is not None
    assert session.commits == 1


def test_admin_refuse_responsable_sans_activer_l_espace_famille(monkeypatch):
    cible = _candidat("responsable")
    session = _SessionFausse(cible)
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: _admin())

    response = admin_router.refuser_demande_responsable(
        SimpleNamespace(), cible.id, "Autorité légale à vérifier", session, None
    )

    assert isinstance(response, RedirectResponse)
    assert cible.role == RoleUtilisateur.ETUDIANT
    assert cible.statut_verification_responsable == "refuse"
    assert cible.motif_refus_responsable == "Autorité légale à vérifier"
    assert session.commits == 1


def test_admin_ne_peut_pas_approuver_un_profil_qui_n_est_pas_son_type(monkeypatch):
    cible = _candidat("responsable")
    session = _SessionFausse(cible)
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: _admin())

    admin_router.approuver_demande_sponsor(SimpleNamespace(), cible.id, session, None)

    assert cible.role == RoleUtilisateur.ETUDIANT
    assert cible.statut_verification_sponsor == "en_attente"
    assert session.commits == 0


def test_admin_voit_distinctement_les_demandes_et_peut_justifier_un_refus():
    racine = Path(__file__).resolve().parents[1]
    template = (racine / "app" / "templates" / "admin_utilisateurs.html").read_text(encoding="utf-8")
    assert "Validation en attente" in template
    assert "Demande refusée" in template
    assert 'name="motif"' in template
    assert "Motif du refus (facultatif)" in template


def test_migration_et_modele_exposent_des_statuts_distincts_pour_sponsor_et_responsable():
    colonnes = set(Utilisateur.__table__.columns.keys())
    attendues = {
        "statut_verification_sponsor",
        "demande_sponsor_le",
        "verification_sponsor_le",
        "verification_sponsor_par_id",
        "motif_refus_sponsor",
        "statut_verification_responsable",
        "demande_responsable_le",
        "verification_responsable_le",
        "verification_responsable_par_id",
        "motif_refus_responsable",
    }
    assert attendues.issubset(colonnes)


def test_websockets_chat_et_tableau_bloquent_les_profils_non_valides():
    racine = Path(__file__).resolve().parents[1]
    cercles = (racine / "app" / "routers" / "cercles_router.py").read_text(encoding="utf-8")
    classe = (racine / "app" / "routers" / "classe_router.py").read_text(encoding="utf-8")

    assert "from ..profile_approval import profil_validation_requise" in cercles
    assert "if profil_validation_requise(utilisateur):" in cercles
    assert "if profil_validation_requise(utilisateur_frais):" in cercles
    assert "from ..profile_approval import profil_validation_requise" in classe
    assert "if utilisateur.banni or profil_validation_requise(utilisateur):" in classe
    assert "if profil_validation_requise(utilisateur_frais):" in classe
