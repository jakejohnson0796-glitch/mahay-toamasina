from __future__ import annotations

from types import SimpleNamespace

from app.main import app
from app.routers.auth_router import _ouvrir_session_authentifiee


CRITICAL_POST_PATHS = {
    "/inscription",
    "/connexion",
    "/connexion/2fa",
    "/mot-de-passe-oublie",
    "/mot-de-passe-oublie/code",
    "/profil/academique",
    "/profil/photo",
    "/profil/photo/supprimer",
    "/profil/bio",
    "/profil/email",
    "/securite/mot-de-passe",
    "/securite/universite",
    "/securite/niveau",
    "/securite/2fa/demarrer",
    "/securite/2fa/confirmer",
    "/securite/2fa/desactiver",
    "/securite/2fa/regenerer-codes-secours",
    "/notifications/{notification_id}/lire",
    "/notifications/lire-toutes",
    "/notifications/inactivite/lue",
    "/documents/upload",
}


def _noms_dependances(route) -> set[str]:
    noms = set()
    for dependency in route.dependant.dependencies:
        fonction = dependency.call
        if fonction is not None:
            noms.add(getattr(fonction, "__name__", repr(fonction)))
    return noms


def test_mutations_critiques_exigent_un_jeton_csrf():
    routes = {route.path: route for route in app.routes if hasattr(route, "methods")}
    for path in CRITICAL_POST_PATHS:
        assert path in routes, f"Route critique absente: {path}"
        route = routes[path]
        assert "POST" in route.methods, f"Route critique sans POST: {path}"
        assert "verifier_csrf" in _noms_dependances(route), f"CSRF absent: {path}"


def test_inscription_ouvre_une_session_avec_fingerprint():
    session = {"_csrf_token": "csrf-test", "ancienne_cle": "a-supprimer"}
    request = SimpleNamespace(session=session)
    utilisateur = SimpleNamespace(id=42)

    # La fonction reelle calcule l'empreinte a partir du modele utilisateur;
    # on la remplace localement pour isoler ce contrat de session.
    import app.routers.auth_router as auth_router
    ancienne_fonction = auth_router.empreinte_session_utilisateur
    try:
        auth_router.empreinte_session_utilisateur = lambda _utilisateur: "empreinte-test"
        _ouvrir_session_authentifiee(request, utilisateur)
    finally:
        auth_router.empreinte_session_utilisateur = ancienne_fonction

    assert request.session == {
        "_csrf_token": "csrf-test",
        "user_id": 42,
        "auth_fingerprint": "empreinte-test",
    }


def test_validation_upload_cote_interface_est_alignee_sur_20_mo():
    from pathlib import Path

    page = (Path(__file__).resolve().parents[1] / "app/templates/document_upload.html").read_text(encoding="utf-8")
    assert "20 * 1024 * 1024" in page
    assert "le fichier dépasse 20 Mo" in page
    assert "10 * 1024 * 1024" not in page


def test_couverture_des_headers_de_securite_critique():
    from app.security_headers import _construire_csp

    csp = _construire_csp("test-nonce")
    for directive in (
        "object-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "script-src-attr 'none'",
    ):
        assert directive in csp
    assert "'unsafe-inline'" not in csp
