"""Tenant membership authorization helpers."""
from __future__ import annotations
from typing import Iterable, Optional
from sqlmodel import Session, select
from .models import Cours, EtablissementPartenaire, InscriptionCours, MembreEtablissement, Utilisateur
ROLE_RESPONSABLE = "responsable"
ROLE_PROFESSEUR = "professeur"
ROLE_ETUDIANT = "etudiant"
ROLES_PEDAGOGIQUES = (ROLE_RESPONSABLE, ROLE_PROFESSEUR)

def membre_actif(session: Session, institution_id: Optional[int], utilisateur_id: Optional[int], roles: Optional[Iterable[str]] = None) -> Optional[MembreEtablissement]:
    if not institution_id or not utilisateur_id:
        return None
    institution = session.get(EtablissementPartenaire, institution_id)
    if not institution or not institution.est_actif:
        return None
    q = select(MembreEtablissement).where(MembreEtablissement.institution_id == institution_id, MembreEtablissement.utilisateur_id == utilisateur_id, MembreEtablissement.est_actif == True)
    if roles:
        q = q.where(MembreEtablissement.role.in_(list(roles)))
    return session.exec(q).first()

def institutions_avec_role(session: Session, utilisateur_id: int, roles: Iterable[str]) -> list[int]:
    rows = session.exec(
        select(MembreEtablissement.institution_id)
        .join(EtablissementPartenaire, MembreEtablissement.institution_id == EtablissementPartenaire.id)
        .where(
            MembreEtablissement.utilisateur_id == utilisateur_id,
            MembreEtablissement.est_actif == True,
            MembreEtablissement.role.in_(list(roles)),
            EtablissementPartenaire.est_actif == True,
        )
    ).all()
    return sorted({int(x) for x in rows})

def assurer_membre(session: Session, institution_id: int, utilisateur_id: int, role: str, ajoute_par_id: Optional[int] = None) -> MembreEtablissement:
    if role not in {ROLE_RESPONSABLE, ROLE_PROFESSEUR, ROLE_ETUDIANT}:
        raise ValueError("Rôle institutionnel invalide.")
    membre = session.exec(select(MembreEtablissement).where(MembreEtablissement.institution_id == institution_id, MembreEtablissement.utilisateur_id == utilisateur_id)).first()
    if membre is None:
        membre = MembreEtablissement(institution_id=institution_id, utilisateur_id=utilisateur_id, role=role, est_actif=True, ajoute_par_id=ajoute_par_id)
    else:
        from datetime import datetime
        membre.role = role
        membre.est_actif = True
        membre.ajoute_par_id = ajoute_par_id
        membre.date_maj = datetime.utcnow()
    session.add(membre)
    return membre

def institution_pour_cours(session: Session, utilisateur: Utilisateur, institution_id: Optional[int]) -> Optional[int]:
    autorisees = institutions_avec_role(session, utilisateur.id, ROLES_PEDAGOGIQUES)
    affiliations = session.exec(
        select(MembreEtablissement.institution_id).where(
            MembreEtablissement.utilisateur_id == utilisateur.id,
            MembreEtablissement.role.in_(list(ROLES_PEDAGOGIQUES)),
        )
    ).all()
    if institution_id is not None:
        if institution_id not in autorisees:
            raise ValueError("Tu n'es pas autorisé à créer un cours dans cet établissement.")
        return institution_id
    if len(autorisees) == 1:
        return autorisees[0]
    if len(autorisees) > 1:
        raise ValueError("Choisis l'établissement auquel rattacher ce cours.")
    if affiliations:
        raise ValueError("Ton rattachement institutionnel est inactif. Contacte l'administration.")
    return None

def peut_gerer_cours(session: Session, cours: Cours, utilisateur: Optional[Utilisateur]) -> bool:
    if not utilisateur:
        return False
    role_global = getattr(utilisateur.role, "value", utilisateur.role)
    if role_global == "admin":
        return True
    if cours.institution_id is None:
        return utilisateur.id == cours.professeur_id
    membre = membre_actif(session, cours.institution_id, utilisateur.id, ROLES_PEDAGOGIQUES)
    if not membre:
        return False
    if membre.role == ROLE_RESPONSABLE:
        return True
    return utilisateur.id == cours.professeur_id

def peut_rejoindre_cours(session: Session, cours: Cours, utilisateur: Optional[Utilisateur]) -> bool:
    if not utilisateur:
        return False
    if cours.institution_id is None:
        role_global = getattr(utilisateur.role, "value", utilisateur.role)
        return role_global == "etudiant"
    # Pour un cours institutionnel, le rôle du membre dans ce tenant prévaut
    # sur son rôle global : un professeur peut aussi être étudiant ailleurs.
    return membre_actif(session, cours.institution_id, utilisateur.id, (ROLE_ETUDIANT,)) is not None

def est_inscrit_cours(session: Session, cours_id: int, utilisateur_id: int) -> bool:
    cours = session.get(Cours, cours_id)
    if not cours:
        return False
    if cours.institution_id is not None and membre_actif(session, cours.institution_id, utilisateur_id, (ROLE_ETUDIANT,)) is None:
        return False
    return session.exec(select(InscriptionCours).where(InscriptionCours.cours_id == cours_id, InscriptionCours.utilisateur_id == utilisateur_id)).first() is not None



def lister_inscriptions_actives(session: Session, cours_id: int):
    """Retourne les inscriptions dont le membre appartient encore au tenant."""
    cours = session.get(Cours, cours_id)
    if not cours:
        return []
    requete = (
        select(InscriptionCours, Utilisateur)
        .join(Utilisateur, InscriptionCours.utilisateur_id == Utilisateur.id)
        .where(InscriptionCours.cours_id == cours_id)
    )
    if cours.institution_id is not None:
        requete = (
            requete
            .join(
                MembreEtablissement,
                MembreEtablissement.utilisateur_id == Utilisateur.id,
            )
            .join(
                EtablissementPartenaire,
                EtablissementPartenaire.id == MembreEtablissement.institution_id,
            )
            .where(
                MembreEtablissement.institution_id == cours.institution_id,
                MembreEtablissement.role == ROLE_ETUDIANT,
                MembreEtablissement.est_actif == True,
                EtablissementPartenaire.est_actif == True,
            )
        )
    return session.exec(requete.order_by(InscriptionCours.date_inscription)).all()


def cours_ids_etudiant_actifs(session: Session, utilisateur_id: int) -> list[int]:
    """Liste les cours auxquels l'étudiant appartient encore dans son tenant."""
    ids = session.exec(
        select(InscriptionCours.cours_id)
        .where(InscriptionCours.utilisateur_id == utilisateur_id)
        .order_by(InscriptionCours.cours_id)
    ).all()
    return [
        int(cours_id) for cours_id in ids
        if est_inscrit_cours(session, int(cours_id), utilisateur_id)
    ]
