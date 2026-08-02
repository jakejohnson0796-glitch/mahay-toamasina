"""
Inscription, connexion, deconnexion.
"""
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from ..database import get_session
from ..models import Utilisateur, RoleUtilisateur, Filiere
from ..auth import hacher_mot_de_passe, verifier_mot_de_passe
from .. import subscription

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/inscription")
def formulaire_inscription(request: Request, session: Session = Depends(get_session)):
    filieres = session.exec(select(Filiere)).all()
    return templates.TemplateResponse(
        request, "register.html", {"filieres": filieres, "erreur": None}
    )


@router.post("/inscription")
def inscription(
    request: Request,
    nom: str = Form(...),
    telephone: str = Form(...),
    mot_de_passe: str = Form(...),
    role: RoleUtilisateur = Form(RoleUtilisateur.ETUDIANT),
    filiere_id: Optional[int] = Form(None),
    session: Session = Depends(get_session),
):
    deja_inscrit = session.exec(select(Utilisateur).where(Utilisateur.telephone == telephone)).first()
    if deja_inscrit:
        filieres = session.exec(select(Filiere)).all()
        return templates.TemplateResponse(
            request,
            "register.html",
            {"filieres": filieres, "erreur": "Ce numero est deja enregistre."},
        )

    utilisateur = Utilisateur(
        nom=nom,
        telephone=telephone,
        mot_de_passe_hash=hacher_mot_de_passe(mot_de_passe),
        role=role,
        filiere_id=filiere_id,
    )
    session.add(utilisateur)
    session.commit()
    session.refresh(utilisateur)

    if utilisateur.role == RoleUtilisateur.ETUDIANT:
        subscription.creer_essai_gratuit(session, utilisateur)

    request.session["user_id"] = utilisateur.id
    return RedirectResponse("/", status_code=303)


@router.get("/connexion")
def formulaire_connexion(request: Request):
    return templates.TemplateResponse(request, "login.html", {"erreur": None})


@router.post("/connexion")
def connexion(
    request: Request,
    telephone: str = Form(...),
    mot_de_passe: str = Form(...),
    session: Session = Depends(get_session),
):
    utilisateur = session.exec(select(Utilisateur).where(Utilisateur.telephone == telephone)).first()
    if not utilisateur or not verifier_mot_de_passe(mot_de_passe, utilisateur.mot_de_passe_hash):
        return templates.TemplateResponse(
            request, "login.html", {"erreur": "Numero ou mot de passe incorrect."}
        )
    if utilisateur.banni:
        return templates.TemplateResponse(
            request, "login.html", {"erreur": "Ce compte a ete suspendu. Contactez un administrateur."}
        )

    request.session["user_id"] = utilisateur.id
    return RedirectResponse("/", status_code=303)


@router.get("/deconnexion")
def deconnexion(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)
