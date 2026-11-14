"""Securite renforcee des actions d'administration.

Le mot de passe de confirmation est distinct du mot de passe de connexion.
Il est demande a chaque POST portant une action d'administration sensible.
Le secret n'est jamais stocke en clair ni dans la session.
"""

import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlmodel import Session
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import empreinte_session_utilisateur, session_utilisateur_valide, verifier_mot_de_passe
from .database import engine
from .models import JournalActionAdmin, RoleUtilisateur, Utilisateur
from .request_limits import limite_corps_requete


LONGUEUR_MIN_CONFIRMATION_ADMIN = 12
MAX_ECHECS_CONFIRMATION_ADMIN = 5
FENETRE_ECHECS_CONFIRMATION_ADMIN = timedelta(minutes=10)
BLOCAGE_ECHECS_CONFIRMATION_ADMIN = timedelta(minutes=5)
TAILLE_MAX_FORMULAIRE_ADMIN = 512 * 1024
TAILLE_MAX_IMPORT_INSTITUTIONNEL = 6 * 1024 * 1024


def limite_formulaire_admin(path: str) -> int:
    """Augmente la limite uniquement pour le formulaire d'import institutionnel."""
    if path == "/admin/inscriptions-institutionnelles/importer":
        return TAILLE_MAX_IMPORT_INSTITUTIONNEL
    return TAILLE_MAX_FORMULAIRE_ADMIN


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
            re.fullmatch(r"/cercles/[0-9]+/supprimer", path) is not None
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
    """Protège les POST admin et toutes les écritures faites en accès supervise.

    En accès supervise, le mot de passe de confirmation est exigé pour chaque
    POST et une ligne d'audit est créée avant l'exécution de la route. Une
    écriture ne part donc pas si le journal ne peut pas être persisté.
    """

    async def dispatch(self, request: Request, call_next):
        mode_supervise = bool(request.session.get("admin_mode_actor_id"))
        if request.method.upper() != "POST" or (
            not action_admin_protegee(request.url.path) and not mode_supervise
        ):
            return await call_next(request)

        user_id = request.session.get("user_id")
        if not user_id:
            if mode_supervise:
                request.session.clear()
                return JSONResponse({"detail": "Session supervise invalide."}, status_code=403)
            return await call_next(request)

        admin_id = request.session.get("admin_mode_actor_id") if mode_supervise else user_id
        cible_id = request.session.get("admin_mode_target_id") if mode_supervise else None

        with Session(engine) as session:
            utilisateur = session.get(Utilisateur, admin_id)
            empreinte_attendue = (
                request.session.get("admin_mode_actor_fingerprint")
                if mode_supervise else request.session.get("auth_fingerprint")
            )
            if (
                not utilisateur
                or utilisateur.banni
                or utilisateur.role != RoleUtilisateur.ADMIN
                or not empreinte_attendue
                or empreinte_session_utilisateur(utilisateur) != empreinte_attendue
            ):
                if mode_supervise:
                    request.session.clear()
                    return JSONResponse(
                        {"detail": "La session administrateur d'origine n'est plus valide."},
                        status_code=403,
                    )
                return await call_next(request)

            if mode_supervise:
                cible = session.get(Utilisateur, user_id)
                roles_autorises = {
                    RoleUtilisateur.ETUDIANT,
                    RoleUtilisateur.PROFESSEUR,
                    RoleUtilisateur.REPETITEUR,
                }
                if (
                    cible_id != user_id
                    or not cible
                    or cible.banni
                    or cible.role not in roles_autorises
                    or cible.id == utilisateur.id
                    or not session_utilisateur_valide(request.session, cible)
                ):
                    request.session.clear()
                    return JSONResponse(
                        {"detail": "Le compte cible de la session supervise n'est plus valide."},
                        status_code=403,
                    )

            # Le corps est mis en cache pour que la dépendance CSRF de la route
            # puisse encore relire le formulaire après ce contrôle.
            longueur_annoncee = request.headers.get("content-length")
            try:
                longueur_annoncee = int(longueur_annoncee) if longueur_annoncee is not None else None
            except ValueError:
                longueur_annoncee = None
            # En mode supervise, conserver les plafonds par route de l'application
            # (notamment les dépôts de documents), plutôt que la limite admin 512 Kio.
            limite_formulaire = (
                limite_corps_requete(request.method, request.url.path)
                if mode_supervise
                else limite_formulaire_admin(request.url.path)
            )
            if longueur_annoncee is not None and longueur_annoncee > limite_formulaire:
                return JSONResponse(
                    {"detail": "Formulaire administrateur trop volumineux."},
                    status_code=413,
                )

            contenu_body = await request.body()
            if len(contenu_body) > limite_formulaire:
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

        identifiant_audit = None
        if mode_supervise:
            try:
                with Session(engine) as audit_session:
                    evenement = JournalActionAdmin(
                        admin_id=admin_id,
                        utilisateur_cible_id=cible_id,
                        methode=request.method.upper(),
                        chemin=request.url.path[:240],
                        statut_http=0,
                    )
                    audit_session.add(evenement)
                    audit_session.commit()
                    audit_session.refresh(evenement)
                    identifiant_audit = evenement.id
            except Exception:
                return JSONResponse(
                    {"detail": "Journalisation indisponible : action annulée par sécurité."},
                    status_code=503,
                )

        try:
            reponse = await call_next(request)
        except Exception:
            if identifiant_audit is not None:
                with Session(engine) as audit_session:
                    evenement = audit_session.get(JournalActionAdmin, identifiant_audit)
                    if evenement:
                        evenement.statut_http = 500
                        audit_session.add(evenement)
                        audit_session.commit()
            raise

        if identifiant_audit is not None:
            with Session(engine) as audit_session:
                evenement = audit_session.get(JournalActionAdmin, identifiant_audit)
                if evenement:
                    evenement.statut_http = reponse.status_code
                    audit_session.add(evenement)
                    audit_session.commit()

        return reponse
