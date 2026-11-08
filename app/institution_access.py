"""Contrôles d'appartenance et d'autorisation multiétablissements.

Ces fonctions centralisent les règles tenant côté serveur. Elles ne prétendent
pas remplacer une isolation PostgreSQL RLS : le schéma et le rôle de connexion
doivent respecter le contrat décrit dans la documentation d'exploitation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import and_, exists, or_
from sqlmodel import Session, select

from .models import (
    Cours,
    EtablissementPartenaire,
    InscriptionCours,
    MembreEtablissement,
    Utilisateur,
)

ROLE_RESPONSABLE = "responsable"
ROLE_PROFESSEUR = "professeur"
ROLE_ETUDIANT = "etudiant"
ROLES_PEDAGOGIQUES = (ROLE_RESPONSABLE, ROLE_PROFESSEUR)
ROLES_INSTITUTIONNELS = (ROLE_RESPONSABLE, ROLE_PROFESSEUR, ROLE_ETUDIANT)


def verrouiller_etablissement(
    session: Session, institution_id: int
) -> Optional[EtablissementPartenaire]:
    """Verrouille la ligne parente jusqu'au commit pour sérialiser les rôles."""
    return session.exec(
        select(EtablissementPartenaire)
        .where(EtablissementPartenaire.id == institution_id)
        .with_for_update()
    ).first()


def membre_actif(
    session: Session,
    institution_id: Optional[int],
    utilisateur_id: Optional[int],
    roles: Optional[Iterable[str]] = None,
) -> Optional[MembreEtablissement]:
    """Retourne une appartenance active à un établissement lui-même actif.

    Une liste de rôles vide signifie « aucun rôle autorisé », et non « tous les
    rôles ». La jointure évite une lecture préalable séparée de l'établissement.
    """
    if institution_id is None or utilisateur_id is None:
        return None

    roles_demandes = tuple(roles) if roles is not None else None
    if roles_demandes is not None and not roles_demandes:
        return None

    requete = (
        select(MembreEtablissement)
        .join(
            EtablissementPartenaire,
            EtablissementPartenaire.id == MembreEtablissement.institution_id,
        )
        .where(
            MembreEtablissement.institution_id == institution_id,
            MembreEtablissement.utilisateur_id == utilisateur_id,
            MembreEtablissement.est_actif.is_(True),
            EtablissementPartenaire.est_actif.is_(True),
        )
    )
    if roles_demandes is not None:
        requete = requete.where(MembreEtablissement.role.in_(roles_demandes))
    return session.exec(requete).first()


def institutions_avec_role(
    session: Session, utilisateur_id: int, roles: Iterable[str]
) -> list[int]:
    """Liste les établissements actifs où l'utilisateur possède un rôle actif."""
    roles_demandes = tuple(roles)
    if not roles_demandes:
        return []

    lignes = session.exec(
        select(MembreEtablissement.institution_id)
        .join(
            EtablissementPartenaire,
            MembreEtablissement.institution_id == EtablissementPartenaire.id,
        )
        .where(
            MembreEtablissement.utilisateur_id == utilisateur_id,
            MembreEtablissement.est_actif.is_(True),
            MembreEtablissement.role.in_(roles_demandes),
            EtablissementPartenaire.est_actif.is_(True),
        )
    ).all()
    return sorted({int(institution_id) for institution_id in lignes})


def assurer_membre(
    session: Session,
    institution_id: int,
    utilisateur_id: int,
    role: str,
    ajoute_par_id: Optional[int] = None,
) -> MembreEtablissement:
    """Crée ou réactive une appartenance après validation par la route appelante."""
    if role not in ROLES_INSTITUTIONNELS:
        raise ValueError("Rôle institutionnel invalide.")

    membre = session.exec(
        select(MembreEtablissement).where(
            MembreEtablissement.institution_id == institution_id,
            MembreEtablissement.utilisateur_id == utilisateur_id,
        )
    ).first()
    if membre is None:
        membre = MembreEtablissement(
            institution_id=institution_id,
            utilisateur_id=utilisateur_id,
            role=role,
            est_actif=True,
            ajoute_par_id=ajoute_par_id,
        )
    else:
        membre.role = role
        membre.est_actif = True
        membre.ajoute_par_id = ajoute_par_id
        membre.date_maj = datetime.utcnow()

    session.add(membre)
    return membre


def institution_pour_cours(
    session: Session, utilisateur: Utilisateur, institution_id: Optional[int]
) -> Optional[int]:
    """Détermine sans supposition le tenant d'un nouveau cours."""
    affiliations = session.exec(
        select(
            MembreEtablissement.institution_id,
            MembreEtablissement.est_actif,
            EtablissementPartenaire.est_actif,
        )
        .join(
            EtablissementPartenaire,
            EtablissementPartenaire.id == MembreEtablissement.institution_id,
        )
        .where(
            MembreEtablissement.utilisateur_id == utilisateur.id,
            MembreEtablissement.role.in_(ROLES_PEDAGOGIQUES),
        )
    ).all()
    autorisees = sorted(
        {
            int(inst_id)
            for inst_id, membre_actif_, institution_active in affiliations
            if membre_actif_ and institution_active
        }
    )

    if institution_id is not None:
        if institution_id not in autorisees:
            raise ValueError(
                "Tu n'es pas autorisé à créer un cours dans cet établissement."
            )
        return institution_id

    if len(autorisees) == 1:
        return autorisees[0]
    if len(autorisees) > 1:
        raise ValueError("Choisis l'établissement auquel rattacher ce cours.")
    if affiliations:
        raise ValueError(
            "Ton rattachement institutionnel est inactif. Contacte l'administration."
        )
    return None


def peut_gerer_cours(
    session: Session, cours: Cours, utilisateur: Optional[Utilisateur]
) -> bool:
    """Vérifie le rôle pédagogique dans le tenant du cours."""
    if not utilisateur:
        return False

    role_global = getattr(utilisateur.role, "value", utilisateur.role)
    if role_global == "admin":
        return True
    if getattr(cours, "affectation_institutionnelle_requise", False):
        # Un cours ambigu est réservé à l'administration globale.
        return False
    if cours.institution_id is None:
        return utilisateur.id == cours.professeur_id

    membre = membre_actif(
        session, cours.institution_id, utilisateur.id, ROLES_PEDAGOGIQUES
    )
    if not membre:
        return False
    if membre.role == ROLE_RESPONSABLE:
        return True
    return utilisateur.id == cours.professeur_id


def peut_rejoindre_cours(
    session: Session, cours: Cours, utilisateur: Optional[Utilisateur]
) -> bool:
    """Vérifie qu'un compte peut rejoindre un cours dans son tenant."""
    if not utilisateur or getattr(cours, "affectation_institutionnelle_requise", False):
        return False
    if cours.institution_id is None:
        role_global = getattr(utilisateur.role, "value", utilisateur.role)
        return role_global == "etudiant"

    return (
        membre_actif(session, cours.institution_id, utilisateur.id, (ROLE_ETUDIANT,))
        is not None
    )


def _appartenance_role_active(
    institution_id_expression,
    utilisateur_id: int,
    roles: Iterable[str],
):
    """Expression SQL corrélée pour vérifier un rôle actif dans le tenant."""
    roles_demandes = tuple(roles)
    if not roles_demandes:
        return False
    return exists(
        select(1)
        .select_from(MembreEtablissement)
        .join(
            EtablissementPartenaire,
            EtablissementPartenaire.id == MembreEtablissement.institution_id,
        )
        .where(
            MembreEtablissement.institution_id == institution_id_expression,
            MembreEtablissement.utilisateur_id == utilisateur_id,
            MembreEtablissement.role.in_(roles_demandes),
            MembreEtablissement.est_actif.is_(True),
            EtablissementPartenaire.est_actif.is_(True),
        )
    )


def _appartenance_etudiante_active(
    institution_id_expression, utilisateur_id: int
):
    """Expression SQL corrélée : appartenance étudiant + établissement actifs."""
    return _appartenance_role_active(
        institution_id_expression, utilisateur_id, (ROLE_ETUDIANT,)
    )


def lister_cours_gerables(
    session: Session, utilisateur: Utilisateur
) -> list[Cours]:
    """Charge les cours administrables sans vérification SQL par ligne."""
    cours_professeur_independants = and_(
        Cours.institution_id.is_(None),
        Cours.professeur_id == utilisateur.id,
    )
    cours_professeur_tenant = and_(
        Cours.professeur_id == utilisateur.id,
        _appartenance_role_active(
            Cours.institution_id, utilisateur.id, ROLES_PEDAGOGIQUES
        ),
    )
    cours_responsable_tenant = _appartenance_role_active(
        Cours.institution_id, utilisateur.id, (ROLE_RESPONSABLE,)
    )
    requete = (
        select(Cours)
        .where(
            Cours.affectation_institutionnelle_requise.is_(False),
            or_(
                cours_professeur_independants,
                cours_professeur_tenant,
                cours_responsable_tenant,
            ),
        )
        .order_by(Cours.date_creation.desc())
    )
    return session.exec(requete).all()


def lister_cours_etudies(
    session: Session, utilisateur_id: int
) -> list[Cours]:
    """Charge les cours suivis dans un seul SELECT, tenant compris."""
    requete = (
        select(Cours)
        .join(InscriptionCours, InscriptionCours.cours_id == Cours.id)
        .where(
            InscriptionCours.utilisateur_id == utilisateur_id,
            Cours.affectation_institutionnelle_requise.is_(False),
            or_(
                Cours.institution_id.is_(None),
                _appartenance_etudiante_active(Cours.institution_id, utilisateur_id),
            ),
        )
        .distinct()
        .order_by(Cours.date_creation.desc())
    )
    return session.exec(requete).all()


def lister_inscriptions_actives_pour_cours(
    session: Session, cours_ids: Iterable[int]
) -> list[tuple[InscriptionCours, Utilisateur]]:
    """Charge les inscriptions valides de plusieurs cours dans un seul SELECT."""
    ids = sorted({int(cours_id) for cours_id in cours_ids if cours_id is not None})
    if not ids:
        return []
    requete = (
        select(InscriptionCours, Utilisateur)
        .join(Cours, Cours.id == InscriptionCours.cours_id)
        .join(Utilisateur, InscriptionCours.utilisateur_id == Utilisateur.id)
        .where(
            Cours.id.in_(ids),
            Cours.affectation_institutionnelle_requise.is_(False),
            or_(
                Cours.institution_id.is_(None),
                _appartenance_etudiante_active(Cours.institution_id, Utilisateur.id),
            ),
        )
        .order_by(InscriptionCours.date_inscription)
    )
    return session.exec(requete).all()


def est_inscrit_cours(
    session: Session, cours_id: int, utilisateur_id: int
) -> bool:
    """Vérifie l'inscription et, si nécessaire, l'appartenance tenant en une requête."""
    resultat = session.exec(
        select(InscriptionCours.id)
        .join(Cours, Cours.id == InscriptionCours.cours_id)
        .where(
            InscriptionCours.cours_id == cours_id,
            InscriptionCours.utilisateur_id == utilisateur_id,
            Cours.affectation_institutionnelle_requise.is_(False),
            or_(
                Cours.institution_id.is_(None),
                _appartenance_etudiante_active(Cours.institution_id, utilisateur_id),
            ),
        )
    ).first()
    return resultat is not None


def lister_inscriptions_actives(
    session: Session, cours_id: int
) -> list[tuple[InscriptionCours, Utilisateur]]:
    """Retourne les inscriptions valides pour le tenant en une requête."""
    return lister_inscriptions_actives_pour_cours(session, (cours_id,))


def cours_ids_etudiant_actifs(
    session: Session, utilisateur_id: int
) -> list[int]:
    """Liste les cours actifs d'un étudiant sans requête supplémentaire par cours."""
    lignes = session.exec(
        select(Cours.id)
        .join(InscriptionCours, InscriptionCours.cours_id == Cours.id)
        .where(
            InscriptionCours.utilisateur_id == utilisateur_id,
            Cours.affectation_institutionnelle_requise.is_(False),
            or_(
                Cours.institution_id.is_(None),
                _appartenance_etudiante_active(Cours.institution_id, utilisateur_id),
            ),
        )
        .order_by(Cours.id)
    ).all()
    return [int(cours_id) for cours_id in lignes]
