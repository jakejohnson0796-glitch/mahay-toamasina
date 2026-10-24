from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from sqlmodel import Session

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..auth import utilisateur_courant
from .. import dashboard as dashboard_module
from .. import learning_recap

router = APIRouter()


@router.get("/dashboard")
def page_dashboard(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    donnees = dashboard_module.donnees_dashboard(session, utilisateur)

    return templates.TemplateResponse(
        request,
        "dashboard_etudiant.html",
        {"utilisateur": utilisateur, **donnees},
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
