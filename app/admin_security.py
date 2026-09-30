"""Securite renforcee des actions d'administration.

Le mot de passe de confirmation est distinct du mot de passe de connexion.
Il est demande a chaque POST portant une action d'administration sensible.
Le secret n'est jamais stocke en clair ni dans la session.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Request
from sqlmodel import Session

from .auth import verifier_mot_de_passe
from .models import RoleUtilisateur, Utilisateur


LONGUEUR_MIN_CONFIRMATION_ADMIN = 12
MAX_ECHECS_CONFIRMATION_ADMIN = 5
FENETRE_ECHECS_CONFIRMATION_ADMIN = timedelta(minutes=10)
BLOCAGE_ECHECS_CONFIRMATION_ADMIN = timedelta(minutes=5)


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
    return bool(
        path.startswith("/cercles/")
        and path.endswith("/supprimer")
    )


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
