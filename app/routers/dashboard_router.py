from fastapi import APIRouter, Request, Depends
from fastapi.responses import Response
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..auth import utilisateur_courant
from .. import dashboard as dashboard_module

router = APIRouter()


@router.get("/dashboard")
def page_dashboard(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    donnees = dashboard_module.donnees_dashboard(session, utilisateur)

    reponse = templates.TemplateResponse(
        request,
        "dashboard_etudiant.html",
        {"utilisateur": utilisateur, **donnees},
    )
    # Le dashboard contient uniquement les données privées de l’utilisateur.
    # Une courte mise en cache navigateur réduit les rechargements inutiles
    # lors des retours/rafraîchissements rapides, sans partager la réponse.
    reponse.headers["Cache-Control"] = "private, max-age=15, stale-while-revalidate=30"
    return reponse
