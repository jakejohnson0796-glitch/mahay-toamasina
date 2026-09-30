from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from ..database import get_session
from ..templating import templates
from ..auth import utilisateur_courant
from .. import gamification

router = APIRouter()


@router.get("/defis")
def page_defis(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    donnees = gamification.donnees_defis(session, utilisateur)
    return templates.TemplateResponse(
        request,
        "defis.html",
        {
            "utilisateur": utilisateur,
            **donnees,
        },
    )
