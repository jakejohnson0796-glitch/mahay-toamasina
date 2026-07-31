"""
Agregation des donnees du tableau de bord etudiant. Separe du router pour
garder celui-ci fin (responsabilite unique : le router orchestre la
requete HTTP, ce module sait comment lire les donnees).
"""
from typing import List

from sqlmodel import Session, select

from .models import CercleEtude, MembreCercle, ConsultationDocument, Document, Utilisateur
from . import subscription

NB_DOCUMENTS_RECENTS = 5


def cercles_rejoints(session: Session, utilisateur_id: int) -> List[dict]:
    """Cercles dont l'etudiant est membre, les plus recemment rejoints
    d'abord."""
    resultats = session.exec(
        select(MembreCercle, CercleEtude)
        .join(CercleEtude, MembreCercle.cercle_id == CercleEtude.id)
        .where(MembreCercle.utilisateur_id == utilisateur_id)
        .order_by(MembreCercle.date_adhesion.desc())
    ).all()
    return [{"cercle": cercle, "date_adhesion": membre.date_adhesion} for membre, cercle in resultats]


def documents_consultes_recemment(session: Session, utilisateur_id: int) -> List[dict]:
    """Les derniers documents consultes par l'etudiant, un seul par
    document (la consultation la plus recente), les plus recents
    d'abord."""
    consultations = session.exec(
        select(ConsultationDocument)
        .where(ConsultationDocument.utilisateur_id == utilisateur_id)
        .order_by(ConsultationDocument.date_consultation.desc())
    ).all()

    vus = set()
    resultats = []
    for c in consultations:
        if c.document_id in vus:
            continue
        vus.add(c.document_id)
        document = session.get(Document, c.document_id)
        if document:
            resultats.append({"document": document, "date_consultation": c.date_consultation})
        if len(resultats) >= NB_DOCUMENTS_RECENTS:
            break
    return resultats


def donnees_dashboard(session: Session, utilisateur: Utilisateur) -> dict:
    """Tout ce qu'il faut pour afficher le tableau de bord etudiant en un
    seul appel depuis le router."""
    abonnement = subscription.obtenir_abonnement(session, utilisateur.id)
    if abonnement:
        abonnement = subscription.synchroniser_expiration(session, abonnement)

    cercles = cercles_rejoints(session, utilisateur.id)
    documents = documents_consultes_recemment(session, utilisateur.id)

    return {
        "abonnement": abonnement,
        "acces_premium": subscription.acces_premium_valide(abonnement),
        "jours_restants": subscription.jours_restants(abonnement),
        "cercles": cercles,
        "documents_recents": documents,
        "nb_cercles_rejoints": len(cercles),
        "nb_documents_consultes": len(
            session.exec(
                select(ConsultationDocument).where(ConsultationDocument.utilisateur_id == utilisateur.id)
            ).all()
        ),
    }
