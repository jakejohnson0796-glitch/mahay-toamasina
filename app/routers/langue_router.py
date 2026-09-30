"""Choix de la langue de l'interface."""
from urllib.parse import urlsplit

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse

from ..csrf import verifier_csrf
from ..i18n import langue_valide

router = APIRouter()


@router.post("/langue")
def changer_langue(
    request: Request,
    langue: str = Form(...),
    _csrf: None = Depends(verifier_csrf),
):
    request.session["langue"] = langue_valide(langue)

    referer = request.headers.get("referer")
    destination = "/"
    if referer:
        cible = urlsplit(referer)
        if cible.netloc == request.url.netloc and cible.path.startswith("/"):
            destination = cible.path or "/"
            if cible.query:
                destination += "?" + cible.query

    return RedirectResponse(destination, status_code=303)
