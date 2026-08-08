"""
Inscription, connexion, deconnexion.
"""
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..models import Utilisateur, RoleUtilisateur, Filiere
from ..auth import hacher_mot_de_passe, verifier_mot_de_passe
from ..rate_limit import limite_depassee
from .. import subscription


def _ip_client(request: Request) -> str:
    return request.client.host if request.client else "inconnu"

router = APIRouter()


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
    _csrf: None = Depends(verifier_csrf),
):
    # Anti-spam : limite la creation automatisee de comptes en masse
    # (chaque etudiant inscrit declenche un essai gratuit — voir
    # subscription.creer_essai_gratuit plus bas, donc un spam
    # d'inscriptions a aussi un cout direct, pas seulement un risque
    # d'abus des cercles/quiz).
    if limite_depassee(f"inscription:ip:{_ip_client(request)}", max_tentatives=8, fenetre_secondes=3600):
        filieres = session.exec(select(Filiere)).all()
        return templates.TemplateResponse(
            request,
            "register.html",
            {"filieres": filieres, "erreur": "Trop de tentatives d'inscription depuis cette adresse. Reessayez plus tard."},
        )

    # SECURITE : le formulaire public (register.html) ne propose que
    # "etudiant" et "sponsor" dans son <select>, mais rien n'empeche un
    # appel direct (curl/Postman/devtools) d'envoyer role=admin. Sans ce
    # garde-fou, n'importe qui obtiendrait un compte administrateur
    # complet en un seul POST non authentifie. Un compte ADMIN ne doit
    # jamais pouvoir naitre de l'auto-inscription : il est cree a la main
    # via app/creer_admin.py (execute par un operateur de confiance ayant
    # deja acces au serveur), jamais via cette route publique.
    if role not in (RoleUtilisateur.ETUDIANT, RoleUtilisateur.SPONSOR):
        role = RoleUtilisateur.ETUDIANT

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
    _csrf: None = Depends(verifier_csrf),
):
    # Anti brute-force : deux limites cumulees.
    # - par IP : empeche un attaquant de tester en rafale plein de
    #   numeros differents depuis une seule machine/script.
    # - par numero cible : protege un compte precis meme si l'attaquant
    #   change d'IP ou passe par un proxy/VPN tournant.
    # Les deux compteurs avancent meme quand la 1ere limite bloque deja,
    # pour qu'un attaquant ne puisse pas "garder sous le seuil" l'un des
    # deux en jouant sur l'ordre des tentatives.
    trop_ip = limite_depassee(f"connexion:ip:{_ip_client(request)}", max_tentatives=15, fenetre_secondes=60)
    trop_tel = limite_depassee(f"connexion:tel:{telephone}", max_tentatives=6, fenetre_secondes=60)
    if trop_ip or trop_tel:
        return templates.TemplateResponse(
            request, "login.html", {"erreur": "Trop de tentatives. Reessayez dans une minute."}
        )

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
