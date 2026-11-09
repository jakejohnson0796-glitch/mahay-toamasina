"""Cloisonnement central des comptes responsables légaux."""

from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import session_utilisateur_valide
from .database import engine
from .models import RoleUtilisateur, Utilisateur


def chemin_autorise_responsable(method: str, path: str, user_id: int) -> bool:
    """Liste blanche des routes permises à un compte responsable."""
    method = (method or "GET").upper()
    if method in {"GET", "HEAD"} and path.startswith("/static/"):
        return True
    if method in {"GET", "HEAD"} and path in {
        "/famille",
        "/securite",
        "/health",
        "/ready",
        "/favicon.ico",
        "/sw.js",
        "/cadre-legal",
        "/conditions-utilisation",
        "/charte-ethique",
        "/confidentialite",
        "/mentions-legales",
        "/faq",
        "/contact",
        "/a-propos",
        "/universites",
        "/mode-emploi",
    }:
        return True
    if method == "POST" and path in {
        "/deconnexion",
        "/securite/mot-de-passe",
    }:
        return True
    if method in {"GET", "POST"} and path.startswith("/securite/2fa/"):
        return True
    if method in {"GET", "HEAD"} and path == f"/profil/photo/{user_id}":
        return True
    return False


class ResponsablePortalMiddleware(BaseHTTPMiddleware):
    """Empêche un compte responsable d'utiliser les fonctionnalités apprenant.

    Le rôle distinct est la première barrière. Le profil est aussi contrôlé
    pour couvrir les comptes historiques/créés avant le rôle dédié. La liste
    blanche ne donne accès qu'au portail famille, à la sécurité du compte,
    aux ressources publiques et à la déconnexion.
    """

    async def dispatch(self, request: Request, call_next):
        user_id = request.session.get("user_id")
        if not user_id:
            return await call_next(request)

        with Session(engine) as session:
            utilisateur = session.get(Utilisateur, user_id)
            if (
                not utilisateur
                or utilisateur.banni
                or not session_utilisateur_valide(request.session, utilisateur)
            ):
                return await call_next(request)

            est_responsable = (
                utilisateur.role == RoleUtilisateur.RESPONSABLE
                or (
                    utilisateur.profil_souhaite == "responsable"
                    and utilisateur.role != RoleUtilisateur.ADMIN
                )
            )
            if est_responsable and not chemin_autorise_responsable(
                request.method, request.url.path, int(user_id)
            ):
                return RedirectResponse("/famille", status_code=303)

        return await call_next(request)
