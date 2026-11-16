from types import SimpleNamespace

from app.models import RoleUtilisateur
from app.routers import auth_router


class _Result:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class _PhotoSession:
    def __init__(self, target=None, shared_circle=None):
        self.target = target
        self.shared_circle = shared_circle
        self.statements = []

    def get(self, _model, _identifier):
        return self.target

    def exec(self, statement):
        self.statements.append(statement)
        return _Result(self.shared_circle)


def _request():
    return SimpleNamespace()


def _target():
    return SimpleNamespace(id=42, photo_chemin="/private/uploads/avatar_42.png")


def test_photo_profil_ne_revele_rien_a_un_visiteur_anonyme(monkeypatch):
    monkeypatch.setattr(auth_router, "utilisateur_courant", lambda *_args: None)
    session = _PhotoSession(target=_target())

    response = auth_router.afficher_photo_profil(_request(), 42, session)

    assert response.status_code == 200
    assert response.media_type == "image/svg+xml"
    assert b"/private/uploads/avatar_42.png" not in response.body
    assert response.headers["cache-control"] == "private, no-store"
    assert not session.statements


def test_photo_profil_est_neutre_pour_un_compte_sans_cercle_commun(monkeypatch):
    visiteur = SimpleNamespace(id=7, role=RoleUtilisateur.ETUDIANT)
    monkeypatch.setattr(auth_router, "utilisateur_courant", lambda *_args: visiteur)
    session = _PhotoSession(target=_target(), shared_circle=None)

    response = auth_router.afficher_photo_profil(_request(), 42, session)

    assert response.status_code == 200
    assert response.media_type == "image/svg+xml"
    assert b"/private/uploads/avatar_42.png" not in response.body
    assert len(session.statements) == 1


def test_photo_profil_est_visible_aux_membres_du_meme_cercle_actif(monkeypatch):
    visiteur = SimpleNamespace(id=7, role=RoleUtilisateur.ETUDIANT)
    monkeypatch.setattr(auth_router, "utilisateur_courant", lambda *_args: visiteur)
    monkeypatch.setattr(auth_router, "stockage_distant_actif", lambda: True)
    monkeypatch.setattr(
        auth_router,
        "obtenir_url_telechargement",
        lambda chemin, expires_in, telechargement: (
            "https://stockage.example/fichier-signe"
            if chemin == "/private/uploads/avatar_42.png"
            and expires_in == 60
            and telechargement is False
            else "https://stockage.example/parametres-inattendus"
        ),
    )
    session = _PhotoSession(target=_target(), shared_circle=123)

    response = auth_router.afficher_photo_profil(_request(), 42, session)

    assert response.status_code == 307
    assert response.headers["location"] == "https://stockage.example/fichier-signe"
    assert response.headers["cache-control"] == "private, no-store"


def test_proprietaire_et_administrateur_n'ont_pas_besoin_d'une_requete_cercle():
    session = _PhotoSession()
    proprietaire = SimpleNamespace(id=42, role=RoleUtilisateur.ETUDIANT)
    administrateur = SimpleNamespace(id=99, role=RoleUtilisateur.ADMIN)

    assert auth_router._peut_voir_photo_profil(session, proprietaire, 42)
    assert auth_router._peut_voir_photo_profil(session, administrateur, 42)
    assert not session.statements
