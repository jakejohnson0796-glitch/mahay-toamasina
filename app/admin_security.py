"""Securite renforcee des actions d'administration.

Le mot de passe de confirmation est distinct du mot de passe de connexion.
Il est demande a chaque POST portant une action d'administration sensible.
Le secret n'est jamais stocke en clair ni dans la session.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlmodel import Session
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import session_utilisateur_valide, verifier_mot_de_passe
from .database import engine
from .models import RoleUtilisateur, Utilisateur


LONGUEUR_MIN_CONFIRMATION_ADMIN = 12
MAX_ECHECS_CONFIRMATION_ADMIN = 5
FENETRE_ECHECS_CONFIRMATION_ADMIN = timedelta(minutes=10)
BLOCAGE_ECHECS_CONFIRMATION_ADMIN = timedelta(minutes=5)
TAILLE_MAX_FORMULAIRE_ADMIN = 512 * 1024


def action_admin_protegee(path: str) -> bool:
    """Indique si un POST correspond a une surface d'administration.

    Les routes /admin/* couvrent le centre d'administration et le referentiel.
    /moderation couvre la moderation historique.
    La suppression d'un cercle est egalement une capacite speciale qu'un admin
    peut exercer depuis l'interface normale des cercles.
    """
    if path == "/admin":
        return True
    if path.startswith("/admin/"):
        return path != "/admin/securite/mot-de-passe-confirmation"
    if path.startswith("/moderation"):
        return True
    if path.startswith("/cercles/"):
        # Ne proteger que les capacites speciales accessibles au createur OU
        # a l'admin, pas les actions ordinaires du salon (message, reaction,
        # demande d'adhesion d'un etudiant, etc.).
        return bool(
            path.endswith("/supprimer")
            or "/membres/ajouter" in path
            or "/membres/" in path and path.endswith("/retirer")
            or "/demandes/" in path and (path.endswith("/accepter") or path.endswith("/refuser"))
            or "/messages/" in path and (path.endswith("/epingler") or path.endswith("/desepingler"))
        )
    return False


def confirmation_admin_configuree(utilisateur: Utilisateur) -> bool:
    return bool(utilisateur.mot_de_passe_confirmation_admin_hash)


def _etat_echecs(request: Request) -> tuple[int, Optional[datetime]]:
    nombre = int(request.session.get("admin_confirmation_echecs", 0) or 0)
    timestamp_texte = request.session.get("admin_confirmation_dernier_echec")
    try:
        timestamp = datetime.fromisoformat(timestamp_texte) if timestamp_texte else None
    except (TypeError, ValueError):
        timestamp = None
    return nombre, timestamp


def confirmation_admin_bloquee(request: Request, maintenant: Optional[datetime] = None) -> bool:
    maintenant = maintenant or datetime.utcnow()
    nombre, dernier_echec = _etat_echecs(request)

    if dernier_echec and maintenant - dernier_echec >= FENETRE_ECHECS_CONFIRMATION_ADMIN:
        request.session.pop("admin_confirmation_echecs", None)
        request.session.pop("admin_confirmation_dernier_echec", None)
        return False

    return nombre >= MAX_ECHECS_CONFIRMATION_ADMIN and bool(
        dernier_echec and maintenant - dernier_echec < BLOCAGE_ECHECS_CONFIRMATION_ADMIN
    )


def enregistrer_echec_confirmation_admin(request: Request, maintenant: Optional[datetime] = None) -> None:
    maintenant = maintenant or datetime.utcnow()
    nombre, dernier_echec = _etat_echecs(request)

    if not dernier_echec or maintenant - dernier_echec >= FENETRE_ECHECS_CONFIRMATION_ADMIN:
        nombre = 0

    request.session["admin_confirmation_echecs"] = nombre + 1
    request.session["admin_confirmation_dernier_echec"] = maintenant.isoformat()


def reinitialiser_echecs_confirmation_admin(request: Request) -> None:
    request.session.pop("admin_confirmation_echecs", None)
    request.session.pop("admin_confirmation_dernier_echec", None)


def verifier_confirmation_admin(
    request: Request,
    utilisateur: Utilisateur,
    mot_de_passe: Optional[str],
) -> tuple[bool, str]:
    """Verifie le secret de confirmation fourni par l'admin courant."""
    if confirmation_admin_bloquee(request):
        return False, "Trop de tentatives incorrectes. Réessayez dans quelques minutes."

    if not confirmation_admin_configuree(utilisateur):
        return False, "Le mot de passe de confirmation administrateur n'est pas encore configuré."

    mot_de_passe = mot_de_passe or ""
    if not verifier_mot_de_passe(mot_de_passe, utilisateur.mot_de_passe_confirmation_admin_hash):
        enregistrer_echec_confirmation_admin(request)
        return False, "Mot de passe de confirmation incorrect."

    reinitialiser_echecs_confirmation_admin(request)
    return True, ""


class AdminActionConfirmationMiddleware(BaseHTTPMiddleware):
    """Bloque les actions admin tant que le secret de confirmation n'est pas valide.

    Le secret est fourni par le formulaire sous forme de champ cache rempli
    par static/js/admin-confirmation.js. Cela donne une vraie enforcement
    serveur : desactiver JavaScript ne permet pas de contourner la protection.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method.upper() != "POST" or not action_admin_protegee(request.url.path):
            return await call_next(request)

        user_id = request.session.get("user_id")
        if not user_id:
            return await call_next(request)

        with Session(engine) as session:
            utilisateur = session.get(Utilisateur, user_id)
            if (
                not utilisateur
                or utilisateur.role != RoleUtilisateur.ADMIN
                or not session_utilisateur_valide(request.session, utilisateur)
            ):
                return await call_next(request)

            # BaseHTTPMiddleware utilise un Request intermediaire. Lire
            # request.form() directement ici consomme le flux body ; la
            # dependance CSRF de la route, executee ensuite, recevrait alors
            # un formulaire vide et repondrait 403. request.body() met le
            # contenu en cache, puis request.form() peut le relire normalement.
            contenu_body = await request.body()
            if len(contenu_body) > TAILLE_MAX_FORMULAIRE_ADMIN:
                return JSONResponse(
                    {"detail": "Formulaire administrateur trop volumineux."},
                    status_code=413,
                )
            formulaire = await request.form()
            mot_de_passe = formulaire.get("admin_confirmation_password")

            if not confirmation_admin_configuree(utilisateur):
                return JSONResponse(
                    {
                        "detail": "Configurez d'abord le mot de passe de confirmation administrateur.",
                        "configuration_url": "/admin/securite?configurer=1",
                    },
                    status_code=428,
                )

            if confirmation_admin_bloquee(request):
                return JSONResponse(
                    {
                        "detail": "Trop de tentatives incorrectes. Réessayez dans quelques minutes.",
                    },
                    status_code=429,
                )

            valide, detail = verifier_confirmation_admin(request, utilisateur, mot_de_passe)
            if not valide:
                return JSONResponse({"detail": detail}, status_code=403)

        return await call_next(request)
