import logging
from typing import Optional

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..auth import utilisateur_courant
from ..models import DemandeMiseAJourCours, Document, RoleUtilisateur, Utilisateur
from .. import dashboard as dashboard_module
from .. import learning_recap

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/dashboard")
def page_dashboard(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    dashboard_module.notifier_echeances_proches(session, utilisateur.id)
    donnees = dashboard_module.donnees_dashboard(session, utilisateur)

    alertes_harmonisation = None
    if (
        utilisateur.role == RoleUtilisateur.PROFESSEUR
        and utilisateur.statut_verification_enseignant == "approuve"
    ):
        demandes_harmonisation = session.exec(
            select(DemandeMiseAJourCours)
            .order_by(DemandeMiseAJourCours.date_creation.desc())
            .limit(12)
        ).all()
        alertes_harmonisation = []
        for demande in demandes_harmonisation:
            document = session.get(Document, demande.document_id)
            auteur = session.get(Utilisateur, demande.auteur_id)
            if document:
                alertes_harmonisation.append(
                    {"demande": demande, "document": document, "auteur": auteur}
                )

    return templates.TemplateResponse(
        request,
        "dashboard_etudiant.html",
        {"utilisateur": utilisateur, **donnees, "alertes_harmonisation": alertes_harmonisation},
    )



@router.get("/api/apprentissage/bilan-reprise")
def api_bilan_reprise(
    request: Request,
    depuis: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """Retourne le bilan privé de l'utilisateur authentifié, sans modifier sa progression."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return JSONResponse(
            {"erreur": "connexion_requise"},
            status_code=401,
            headers={"Cache-Control": "no-store"},
        )

    try:
        bilan = learning_recap.construire_bilan(session, utilisateur, depuis=depuis)
    except Exception:
        # Pas de détail interne, contenu d'apprentissage ou prompt dans la réponse HTTP.
        logger.exception("Échec du bilan de reprise pour utilisateur_id=%s", utilisateur.id)
        return JSONResponse(
            {"erreur": "bilan_indisponible"},
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )

    return JSONResponse(bilan, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
