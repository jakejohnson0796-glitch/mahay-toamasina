"""Bloque les sessions institutionnelles jusqu'au choix d'un mot de passe personnel."""
from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import session_utilisateur_valide
from .database import engine
from .models import Utilisateur


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
        if not user_id or chemin_autorise_pendant_changement(
            request.method, request.url.path
        ):
            return await call_next(request)

        with Session(engine) as session:
            utilisateur = session.get(Utilisateur, user_id)
            if (
                utilisateur
                and not utilisateur.banni
                and utilisateur.doit_changer_mot_de_passe
                and session_utilisateur_valide(request.session, utilisateur)
            ):
                return RedirectResponse("/securite?obligatoire=1", status_code=303)

        return await call_next(request)
