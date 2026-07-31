from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from ..database import get_session
from ..auth import utilisateur_courant
from .. import dashboard as dashboard_module

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


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
