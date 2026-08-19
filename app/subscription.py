"""
Logique metier de l'acces Premium etudiant : essai gratuit de 14 jours,
puis abonnement paye de 5 000 Ar/mois valide manuellement par un admin.

Centralise ici (plutot que disperse dans les routers) pour respecter le
principe de responsabilite unique : les routers orchestrent la requete
HTTP, ce module decide seul de ce qui constitue un acces Premium valide.
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from .models import AbonnementEtudiant, StatutAbonnementEtudiant, Utilisateur

DUREE_ESSAI_JOURS = 14
PRIX_ABONNEMENT_ETUDIANT_ARIARY = 5_000
DUREE_PROLONGATION_JOURS = 30


def creer_essai_gratuit(session: Session, utilisateur: Utilisateur) -> AbonnementEtudiant:
    """Cree l'abonnement en essai gratuit pour un nouvel etudiant.
    Appele une seule fois, juste apres l'inscription. Si un enregistrement
    existe deja pour cet utilisateur (ne devrait pas arriver vu la
    contrainte unique, mais on reste defensif), on le renvoie tel quel
    plutot que de planter."""
    existant = obtenir_abonnement(session, utilisateur.id)
    if existant:
        return existant

    maintenant = datetime.utcnow()
    abonnement = AbonnementEtudiant(
        utilisateur_id=utilisateur.id,
        statut=StatutAbonnementEtudiant.ESSAI,
        date_debut_essai=maintenant,
        date_fin_essai=maintenant + timedelta(days=DUREE_ESSAI_JOURS),
    )
    session.add(abonnement)
    session.commit()
    session.refresh(abonnement)
    return abonnement


def obtenir_abonnement(session: Session, utilisateur_id: int) -> Optional[AbonnementEtudiant]:
    return session.exec(
        select(AbonnementEtudiant).where(AbonnementEtudiant.utilisateur_id == utilisateur_id)
    ).first()


def _date_fin_effective(abonnement: AbonnementEtudiant) -> datetime:
    """Date au-dela de laquelle l'acces Premium n'est plus valide, compte
    tenu du statut actuel (essai ou abonnement paye)."""
    if abonnement.statut == StatutAbonnementEtudiant.ACTIF and abonnement.date_fin_abonnement:
        return abonnement.date_fin_abonnement
    return abonnement.date_fin_essai


def synchroniser_expiration(session: Session, abonnement: AbonnementEtudiant) -> AbonnementEtudiant:
    """Fait passer l'abonnement en EXPIRE si sa date de fin effective est
    depassee et qu'il n'est pas deja dans un etat terminal/en attente.
    A appeler avant toute lecture de statut affichee a l'utilisateur ou
    utilisee pour une decision d'acces, car le passage a EXPIRE ne se fait
    pas via une tache planifiee mais paresseusement, a la lecture."""
    if abonnement.statut not in (StatutAbonnementEtudiant.ESSAI, StatutAbonnementEtudiant.ACTIF):
        return abonnement

    if datetime.utcnow() > _date_fin_effective(abonnement):
        abonnement.statut = StatutAbonnementEtudiant.EXPIRE
        abonnement.date_maj = datetime.utcnow()
        session.add(abonnement)
        session.commit()
        session.refresh(abonnement)

    return abonnement


def acces_premium_valide(abonnement: Optional[AbonnementEtudiant]) -> bool:
    """True si l'etudiant a acces aux fonctionnalites Premium en ce moment.
    Suppose que synchroniser_expiration() a deja ete appele sur cet
    abonnement dans le meme cycle requete/reponse.

    Important : l'essai gratuit reste valable jusqu'a sa date de fin quel
    que soit le statut courant. Sans ca, un etudiant qui soumet sa preuve
    de paiement (statut -> EN_ATTENTE) perdrait l'acces Premium pendant
    que l'admin traite sa demande, alors qu'il lui restait des jours
    d'essai — ca punirait les etudiants proactifs qui paient a l'avance."""
    if abonnement is None:
        return False
    maintenant = datetime.utcnow()
    if maintenant <= abonnement.date_fin_essai:
        return True
    if abonnement.statut == StatutAbonnementEtudiant.ACTIF:
        return bool(abonnement.date_fin_abonnement) and maintenant <= abonnement.date_fin_abonnement
    return False


def jours_restants(abonnement: Optional[AbonnementEtudiant]) -> int:
    """Nombre de jours restants avant expiration (0 si deja expire/absent).
    Utilise pour l'affichage ('Essai : 12 jours restants') sur le tableau
    de bord et dans la navigation."""
    if abonnement is None or not acces_premium_valide(abonnement):
        return 0
    delta = _date_fin_effective(abonnement) - datetime.utcnow()
    return max(delta.days, 0)


def soumettre_demande_abonnement(
    session: Session,
    abonnement: AbonnementEtudiant,
    fournisseur_paiement: str,
    reference_paiement: Optional[str],
    preuve_paiement_chemin: Optional[str],
) -> AbonnementEtudiant:
    """L'etudiant soumet sa demande d'abonnement payant (avec ou apres son
    essai). Passe en EN_ATTENTE : c'est un admin qui decidera ensuite."""
    abonnement.statut = StatutAbonnementEtudiant.EN_ATTENTE
    abonnement.fournisseur_paiement = fournisseur_paiement
    abonnement.reference_paiement = reference_paiement
    abonnement.preuve_paiement_chemin = preuve_paiement_chemin
    abonnement.motif_refus = None
    abonnement.date_maj = datetime.utcnow()
    session.add(abonnement)
    session.commit()
    session.refresh(abonnement)
    return abonnement


def valider_abonnement(session: Session, abonnement: AbonnementEtudiant, admin_id: int) -> AbonnementEtudiant:
    """Action admin : valide le paiement. Ajoute toujours
    DUREE_PROLONGATION_JOURS (30j) a partir de maintenant, ou a partir de
    la date de fin actuelle si l'abonnement etait deja actif et pas encore
    expire (renouvellement anticipe : pas de jours perdus)."""
    maintenant = datetime.utcnow()
    point_de_depart = maintenant
    if abonnement.statut == StatutAbonnementEtudiant.ACTIF and abonnement.date_fin_abonnement and abonnement.date_fin_abonnement > maintenant:
        point_de_depart = abonnement.date_fin_abonnement

    abonnement.statut = StatutAbonnementEtudiant.ACTIF
    abonnement.date_fin_abonnement = point_de_depart + timedelta(days=DUREE_PROLONGATION_JOURS)
    abonnement.valide_par_admin_id = admin_id
    abonnement.date_derniere_action_admin = maintenant
    abonnement.motif_refus = None
    abonnement.date_maj = maintenant
    session.add(abonnement)
    session.commit()
    session.refresh(abonnement)
    return abonnement


def refuser_abonnement(session: Session, abonnement: AbonnementEtudiant, admin_id: int, motif: Optional[str] = None) -> AbonnementEtudiant:
    """Action admin : rejette la demande (ex: preuve de paiement invalide).
    L'etudiant retombe sans acces Premium (sauf s'il est encore dans son
    essai gratuit, auquel cas acces_premium_valide() continue de se baser
    sur date_fin_essai)."""
    maintenant = datetime.utcnow()
    abonnement.statut = StatutAbonnementEtudiant.REFUSE
    abonnement.valide_par_admin_id = admin_id
    abonnement.date_derniere_action_admin = maintenant
    abonnement.motif_refus = motif
    abonnement.date_maj = maintenant
    session.add(abonnement)
    session.commit()
    session.refresh(abonnement)
    return abonnement


def prolonger_abonnement(session: Session, abonnement: AbonnementEtudiant, admin_id: int, jours: int = DUREE_PROLONGATION_JOURS) -> AbonnementEtudiant:
    """Action admin : prolonge manuellement (geste commercial, correction
    d'erreur...) sans passer par le circuit de validation d'une demande."""
    maintenant = datetime.utcnow()
    base = abonnement.date_fin_abonnement if (abonnement.date_fin_abonnement and abonnement.date_fin_abonnement > maintenant) else maintenant
    abonnement.statut = StatutAbonnementEtudiant.ACTIF
    abonnement.date_fin_abonnement = base + timedelta(days=jours)
    abonnement.valide_par_admin_id = admin_id
    abonnement.date_derniere_action_admin = maintenant
    abonnement.date_maj = maintenant
    session.add(abonnement)
    session.commit()
    session.refresh(abonnement)
    return abonnement
