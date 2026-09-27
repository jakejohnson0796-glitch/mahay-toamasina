"""Mode d'emploi public de Gasy Mahay.

Cette page centralise le parcours de prise en main du site, avec des etapes
visuelles et des explications qui correspondent aux fonctionnalites reelles
de l'application.
"""
from fastapi import APIRouter, Request, Depends
from sqlmodel import Session

from ..auth import utilisateur_courant
from ..database import get_session
from ..templating import templates

router = APIRouter()


@router.get("/mode-emploi")
def page_mode_emploi(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    return templates.TemplateResponse(
        request,
        "mode_emploi.html",
        {"utilisateur": utilisateur},
    )
