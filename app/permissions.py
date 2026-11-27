"""Central RBAC policy for MITARIDALA.

The policy layer complements (rather than replaces) resource-specific query
filters. Every sensitive route must call these functions on the server; hiding
navigation links is never an authorization check.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from sqlmodel import Session, select

from .models import (
    InscriptionCours,
    LienResponsableEleve,
    MembreCercle,
    MembreEtablissement,
    RoleMembreEtablissement,
    RoleUtilisateur,
    StatutMembreEtablissement,
    Utilisateur,
)
from .profile_approval import profil_validation_requise


class Permission(str, Enum):
    # Global platform powers. At this stage they are reserved to the global
    # administrator; delegated staff roles will require an explicit grant model.
    PLATFORM_USERS_MANAGE = "platform.users.manage"
    PLATFORM_PROFILES_APPROVE = "platform.profiles.approve"
    PLATFORM_DOCUMENTS_MODERATE = "platform.documents.moderate"
    PLATFORM_NATIONAL_CONTENT_REVIEW = "platform.national_content.review"
    PLATFORM_FINANCE_MANAGE = "platform.finance.manage"
    PLATFORM_INSTITUTIONS_MANAGE = "platform.institutions.manage"
    PLATFORM_SECURITY_MANAGE = "platform.security.manage"
    PLATFORM_AUDIT_READ = "platform.audit.read"

    TEACHING_TOOLS = "teaching.tools"
    TEACHING_COURSE_MANAGE = "teaching.course.manage"
    TEACHING_UPDATE_SUBMIT = "teaching.update.submit"
    TEACHING_UPDATE_REVIEW = "teaching.update.review"

    COURSE_ACCESS = "course.access"
    COURSE_MANAGE = "course.manage"

    INSTITUTION_MEMBERS_VIEW = "institution.members.view"
    INSTITUTION_MEMBERS_MANAGE = "institution.members.manage"
    INSTITUTION_ROLE_ASSIGN = "institution.role.assign"

    CIRCLE_ACCESS = "circle.access"
    CIRCLE_MANAGE = "circle.manage"

    FAMILY_PORTAL_VIEW = "family.portal.view"
    FAMILY_CHILD_VIEW = "family.child.view"
    FAMILY_BULLETIN_VIEW = "family.bulletin.view"

    REPETITEUR_PROFILE_MANAGE = "repetiteur.profile.manage"
    REPETITEUR_REQUEST_RESPOND = "repetiteur.request.respond"
    SPONSOR_PROFILE_MANAGE = "sponsor.profile.manage"
    SPONSOR_PARTNERSHIP_REQUEST = "sponsor.partnership.request"


GLOBAL_ADMIN_PERMISSIONS = frozenset(
    permission.value
    for permission in Permission
    if permission.value.startswith("platform.")
    or permission in {
        Permission.TEACHING_UPDATE_REVIEW,
        Permission.TEACHING_TOOLS,
        Permission.TEACHING_COURSE_MANAGE,
        Permission.COURSE_MANAGE,
        Permission.INSTITUTION_MEMBERS_VIEW,
        Permission.INSTITUTION_MEMBERS_MANAGE,
        Permission.INSTITUTION_ROLE_ASSIGN,
        Permission.CIRCLE_ACCESS,
        Permission.CIRCLE_MANAGE,
    }
)


def role_value(utilisateur: Any) -> str:
    role = getattr(utilisateur, "role", None)
    return str(getattr(role, "value", role) or "").strip().lower()


def est_administrateur_global(utilisateur: Optional[Utilisateur]) -> bool:
    """True only for a non-banned account carrying the global admin role."""
    return bool(
        utilisateur
        and not getattr(utilisateur, "banni", False)
        and role_value(utilisateur) == RoleUtilisateur.ADMIN.value
    )


def compte_actif(utilisateur: Optional[Utilisateur]) -> bool:
    """Reject banned accounts and non-student profiles awaiting/denied review."""
    if not utilisateur or getattr(utilisateur, "banni", False):
        return False
    if est_administrateur_global(utilisateur):
        return True
    return not profil_validation_requise(utilisateur)


def profil_approuve(utilisateur: Optional[Utilisateur], profil: str) -> bool:
    """Check effective role, explicit approval status, and profile consistency.

    A missing profil_souhaite is tolerated only for lightweight legacy/test
    objects. Persisted user rows always have this field and must match.
    """
    if not compte_actif(utilisateur) or role_value(utilisateur) != profil:
        return False
    profil_demande = getattr(utilisateur, "profil_souhaite", None)
    if profil_demande not in (None, "", profil):
        return False
    champ_statut = {
        "professeur": "statut_verification_enseignant",
        "repetiteur": "statut_verification_repetiteur",
        "sponsor": "statut_verification_sponsor",
        "responsable": "statut_verification_responsable",
    }.get(profil)
    return bool(champ_statut and getattr(utilisateur, champ_statut, None) == "approuve")


def professeur_approuve(utilisateur: Optional[Utilisateur]) -> bool:
    return profil_approuve(utilisateur, RoleUtilisateur.PROFESSEUR.value)


def responsable_approuve(utilisateur: Optional[Utilisateur]) -> bool:
    return profil_approuve(utilisateur, RoleUtilisateur.RESPONSABLE.value)


def repetiteur_approuve(utilisateur: Optional[Utilisateur]) -> bool:
    return profil_approuve(utilisateur, RoleUtilisateur.REPETITEUR.value)


def sponsor_approuve(utilisateur: Optional[Utilisateur]) -> bool:
    return profil_approuve(utilisateur, RoleUtilisateur.SPONSOR.value)


def peut_gerer_cours(cours: Any, utilisateur: Optional[Utilisateur]) -> bool:
    """Course owner or global admin; a teacher must still be approved."""
    if not compte_actif(utilisateur) or cours is None:
        return False
    return est_administrateur_global(utilisateur) or bool(
        professeur_approuve(utilisateur)
        and getattr(utilisateur, "id", None) == getattr(cours, "professeur_id", None)
    )


def peut_voir_enfant(session: Session, responsable: Optional[Utilisateur], eleve_id: int) -> bool:
    """A responsible adult can see only an explicitly verified active child link."""
    if not responsable_approuve(responsable):
        return False
    eleve = session.get(Utilisateur, eleve_id)
    if (
        not eleve
        or getattr(eleve, "banni", False)
        or role_value(eleve) != RoleUtilisateur.ETUDIANT.value
        or profil_validation_requise(eleve)
    ):
        return False
    return session.exec(
        select(LienResponsableEleve).where(
            LienResponsableEleve.responsable_id == responsable.id,
            LienResponsableEleve.eleve_id == eleve_id,
            LienResponsableEleve.statut == "actif",
        )
    ).first() is not None


ROLE_MEMBRE_RANG = {
    RoleMembreEtablissement.ETUDIANT.value: 1,
    RoleMembreEtablissement.ENSEIGNANT.value: 2,
    RoleMembreEtablissement.GESTIONNAIRE.value: 3,
    RoleMembreEtablissement.RESPONSABLE.value: 4,
}


def roles_institution_assignables(
    role_acteur: str | None, administrateur_global: bool = False
) -> list[str]:
    if administrateur_global:
        return [
            RoleMembreEtablissement.RESPONSABLE.value,
            RoleMembreEtablissement.GESTIONNAIRE.value,
            RoleMembreEtablissement.ENSEIGNANT.value,
            RoleMembreEtablissement.ETUDIANT.value,
        ]
    role = str(getattr(role_acteur, "value", role_acteur) or "")
    if role == RoleMembreEtablissement.RESPONSABLE.value:
        return [
            RoleMembreEtablissement.GESTIONNAIRE.value,
            RoleMembreEtablissement.ENSEIGNANT.value,
            RoleMembreEtablissement.ETUDIANT.value,
        ]
    if role == RoleMembreEtablissement.GESTIONNAIRE.value:
        return [
            RoleMembreEtablissement.ENSEIGNANT.value,
            RoleMembreEtablissement.ETUDIANT.value,
        ]
    return []


def peut_gerer_role_institution(
    role_acteur: str | None,
    role_cible: str | None,
    administrateur_global: bool = False,
) -> bool:
    if administrateur_global:
        return True
    acteur = str(getattr(role_acteur, "value", role_acteur) or "")
    cible = str(getattr(role_cible, "value", role_cible) or "")
    return ROLE_MEMBRE_RANG.get(acteur, 0) > ROLE_MEMBRE_RANG.get(cible, 99)


def _membre_institution_actif(
    session: Session, utilisateur_id: int, institution_id: int
) -> Optional[MembreEtablissement]:
    return session.exec(
        select(MembreEtablissement).where(
            MembreEtablissement.utilisateur_id == utilisateur_id,
            MembreEtablissement.institution_id == institution_id,
            MembreEtablissement.statut == StatutMembreEtablissement.ACTIF.value,
        )
    ).first()


def has_permission(
    utilisateur: Optional[Utilisateur],
    permission: Permission | str,
    *,
    session: Optional[Session] = None,
    resource: Any = None,
    institution_id: Optional[int] = None,
    target_member: Optional[MembreEtablissement] = None,
    target_role: Optional[str] = None,
    child_id: Optional[int] = None,
) -> bool:
    """Evaluate a permission with its required resource scope.

    Unknown permissions fail closed. Global administrators are intentionally
    the only platform-wide authority in this first RBAC rollout.
    """
    try:
        cle = permission.value if isinstance(permission, Permission) else str(permission)
    except (AttributeError, TypeError):
        return False
    if cle not in {item.value for item in Permission}:
        return False
    if not compte_actif(utilisateur):
        return False

    if est_administrateur_global(utilisateur):
        return cle in GLOBAL_ADMIN_PERMISSIONS or cle in {
            Permission.REPETITEUR_PROFILE_MANAGE.value,
            Permission.SPONSOR_PROFILE_MANAGE.value,
            Permission.SPONSOR_PARTNERSHIP_REQUEST.value,
            Permission.REPETITEUR_REQUEST_RESPOND.value,
        }

    if cle == Permission.TEACHING_TOOLS.value:
        return professeur_approuve(utilisateur)
    if cle == Permission.TEACHING_COURSE_MANAGE.value:
        return professeur_approuve(utilisateur)
    if cle == Permission.TEACHING_UPDATE_SUBMIT.value:
        return professeur_approuve(utilisateur)
    if cle == Permission.COURSE_MANAGE.value:
        return peut_gerer_cours(resource, utilisateur)
    if cle == Permission.COURSE_ACCESS.value:
        if (
            session is None
            or resource is None
            or role_value(utilisateur) != RoleUtilisateur.ETUDIANT.value
            or getattr(resource, "id", None) is None
        ):
            return False
        return session.exec(
            select(InscriptionCours).where(
                InscriptionCours.cours_id == resource.id,
                InscriptionCours.utilisateur_id == utilisateur.id,
            )
        ).first() is not None
    if cle == Permission.INSTITUTION_MEMBERS_VIEW.value:
        if session is None or institution_id is None:
            return False
        membre = _membre_institution_actif(session, utilisateur.id, institution_id)
        return bool(
            membre
            and membre.role in {
                RoleMembreEtablissement.RESPONSABLE.value,
                RoleMembreEtablissement.GESTIONNAIRE.value,
            }
        )
    if cle in {
        Permission.INSTITUTION_MEMBERS_MANAGE.value,
        Permission.INSTITUTION_ROLE_ASSIGN.value,
    }:
        if session is None or institution_id is None:
            return False
        membre_acteur = _membre_institution_actif(session, utilisateur.id, institution_id)
        if (
            not membre_acteur
            or membre_acteur.role not in {
                RoleMembreEtablissement.RESPONSABLE.value,
                RoleMembreEtablissement.GESTIONNAIRE.value,
            }
        ):
            return False
        if target_member is not None:
            if target_member.institution_id != institution_id:
                return False
            if not peut_gerer_role_institution(membre_acteur.role, target_member.role):
                return False
        if cle == Permission.INSTITUTION_ROLE_ASSIGN.value:
            return target_role in roles_institution_assignables(membre_acteur.role)
        return True
    if cle == Permission.CIRCLE_ACCESS.value:
        if session is None or resource is None or getattr(resource, "id", None) is None:
            return False
        return session.exec(
            select(MembreCercle).where(
                MembreCercle.cercle_id == resource.id,
                MembreCercle.utilisateur_id == utilisateur.id,
            )
        ).first() is not None
    if cle == Permission.CIRCLE_MANAGE.value:
        return bool(
            resource is not None
            and getattr(resource, "statut", None) == "actif"
            and getattr(resource, "createur_id", None) == utilisateur.id
        )
    if cle == Permission.FAMILY_PORTAL_VIEW.value:
        return responsable_approuve(utilisateur)
    if cle in {
        Permission.FAMILY_CHILD_VIEW.value,
        Permission.FAMILY_BULLETIN_VIEW.value,
    }:
        identifiant = child_id
        if identifiant is None and resource is not None:
            identifiant = getattr(resource, "utilisateur_id", None)
        if identifiant is None or session is None:
            return False
        return peut_voir_enfant(session, utilisateur, int(identifiant))
    if cle == Permission.REPETITEUR_PROFILE_MANAGE.value:
        return repetiteur_approuve(utilisateur)
    if cle == Permission.REPETITEUR_REQUEST_RESPOND.value:
        return bool(
            repetiteur_approuve(utilisateur)
            and resource is not None
            and getattr(resource, "repetiteur_id", None) == utilisateur.id
            and getattr(resource, "statut", None) == "en_attente"
        )
    if cle == Permission.SPONSOR_PROFILE_MANAGE.value:
        return sponsor_approuve(utilisateur)
    if cle == Permission.SPONSOR_PARTNERSHIP_REQUEST.value:
        return sponsor_approuve(utilisateur)
    # All remaining platform-level permissions and review permissions are
    # reserved for the global administrator.
    return False
