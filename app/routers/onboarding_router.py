from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from ..database import get_session
from ..templating import templates
from ..auth import utilisateur_courant
from .. import onboarding

router = APIRouter()


@router.get("/bienvenue")
def page_bienvenue(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    donnees = onboarding.donnees_onboarding(session, utilisateur)
    return templates.TemplateResponse(
        request,
        "bienvenue.html",
        {
            "utilisateur": utilisateur,
            **donnees,
        },
    )
