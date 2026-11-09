"""Bloque les sessions institutionnelles jusqu'au choix d'un mot de passe personnel."""
from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import session_utilisateur_valide
from .database import engine
from .models import RoleUtilisateur, Utilisateur
from .responsable_portal import chemin_autorise_responsable


def chemin_autorise_pendant_changement(method: str, path: str) -> bool:
    """Ne laisse passer que le changement de mot de passe et les ressources nécessaires."""
    method = (method or "GET").upper()
    if path in {"/securite", "/health", "/ready", "/favicon.ico"} and method in {"GET", "HEAD"}:
        return True
    if path == "/securite/mot-de-passe" and method == "POST":
        return True
    if path == "/deconnexion" and method == "POST":
        return True
    if path.startswith("/static/") and method in {"GET", "HEAD"}:
        return True
    return False


class ForcePasswordChangeMiddleware(BaseHTTPMiddleware):
    """Applique réellement le drapeau déjà utilisé après réinitialisation admin."""

    async def dispatch(self, request: Request, call_next):
        user_id = request.session.get("user_id")
        if not user_id:
            return await call_next(request)

        try:
            user_id_int = int(user_id)
        except (TypeError, ValueError):
            return await call_next(request)

        # Les ressources statiques et endpoints de santé ne nécessitent
        # aucune lecture utilisateur ni contrôle de route privée.
        if (
            request.url.path.startswith("/static/")
            or request.url.path in {"/sw.js", "/health", "/ready", "/favicon.ico"}
        ):
            return await call_next(request)

        with Session(engine) as session:
            utilisateur = session.get(Utilisateur, user_id_int)
            if (
                utilisateur
                and not utilisateur.banni
                and session_utilisateur_valide(request.session, utilisateur)
            ):
                # La politique de changement obligatoire reste prioritaire
                # sur le cloisonnement du portail responsable.
                if (
                    utilisateur.doit_changer_mot_de_passe
                    and not chemin_autorise_pendant_changement(
                        request.method, request.url.path
                    )
                ):
                    return RedirectResponse("/securite?obligatoire=1", status_code=303)

                est_responsable = (
                    utilisateur.role == RoleUtilisateur.RESPONSABLE
                    or (
                        utilisateur.profil_souhaite == "responsable"
                        and utilisateur.role != RoleUtilisateur.ADMIN
                    )
                )
                if est_responsable and not chemin_autorise_responsable(
                    request.method, request.url.path, user_id_int
                ):
                    return RedirectResponse("/famille", status_code=303)

        return await call_next(request)
