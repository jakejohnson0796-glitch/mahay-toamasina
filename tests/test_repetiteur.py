from types import SimpleNamespace

from fastapi.responses import RedirectResponse

from app.models import RoleUtilisateur
from app.routers import admin_router


def _admin():
    return SimpleNamespace(id=7, role=RoleUtilisateur.ADMIN)


def _pending_repetiteur():
    return SimpleNamespace(
        id=21,
        role=RoleUtilisateur.ETUDIANT,
        profil_souhaite="repetiteur",
        statut_verification_repetiteur="en_attente",
        verification_repetiteur_le=None,
        verification_repetiteur_par_id=None,
        motif_refus_repetiteur=None,
    )


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


def test_admin_approuve_seulement_une_demande_repetiteur_en_attente(monkeypatch):
    cible = _pending_repetiteur()
    session = _SessionFausse(cible)
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: _admin())

    reponse = admin_router.approuver_demande_repetiteur(
        SimpleNamespace(), cible.id, session, None
    )

    assert isinstance(reponse, RedirectResponse)
    assert reponse.status_code == 303
    assert cible.role == RoleUtilisateur.REPETITEUR
    assert cible.statut_verification_repetiteur == "approuve"
    assert cible.verification_repetiteur_par_id == 7
    assert cible.verification_repetiteur_le is not None
    assert session.commits == 1


def test_admin_peut_refuser_une_demande_sans_accorder_le_role(monkeypatch):
    cible = _pending_repetiteur()
    session = _SessionFausse(cible)
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: _admin())

    reponse = admin_router.refuser_demande_repetiteur(
        SimpleNamespace(), cible.id, "Informations à compléter", session, None
    )

    assert isinstance(reponse, RedirectResponse)
    assert reponse.status_code == 303
    assert cible.role == RoleUtilisateur.ETUDIANT
    assert cible.statut_verification_repetiteur == "refuse"
    assert cible.verification_repetiteur_par_id == 7
    assert cible.motif_refus_repetiteur == "Informations à compléter"
    assert session.commits == 1


def test_admin_ne_peut_pas_approuver_un_compte_sponsor(monkeypatch):
    cible = _pending_repetiteur()
    cible.profil_souhaite = "sponsor"
    session = _SessionFausse(cible)
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: _admin())

    admin_router.approuver_demande_repetiteur(
        SimpleNamespace(), cible.id, session, None
    )

    assert cible.role == RoleUtilisateur.ETUDIANT
    assert cible.statut_verification_repetiteur == "en_attente"
    assert session.commits == 0


def test_demande_repetiteur_refusee_ne_peut_pas_etre_approuvee_sans_nouvelle_demande(monkeypatch):
    cible = _pending_repetiteur()
    cible.statut_verification_repetiteur = "refuse"
    session = _SessionFausse(cible)
    monkeypatch.setattr(admin_router, "_admin_requis", lambda *_args: _admin())

    admin_router.approuver_demande_repetiteur(
        SimpleNamespace(), cible.id, session, None
    )

    assert cible.role == RoleUtilisateur.ETUDIANT
    assert cible.statut_verification_repetiteur == "refuse"
    assert session.commits == 0
