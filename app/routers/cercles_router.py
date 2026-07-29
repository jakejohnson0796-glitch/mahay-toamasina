"""
Cercles d'etude : salons de discussion pour que les etudiants s'entraident
et revisent ensemble, en plus du depot de documents. Chat en temps reel
via WebSocket FastAPI natif (pas de service tiers) : ca reste 100% Python
et coherent avec le reste du projet (voir README, section "choix
techniques" — pas de framework JS pour ce MVP).

L'authentification du WebSocket reutilise directement le cookie de session
existant (SessionMiddleware, deja installe dans main.py) : pas besoin de
mecanisme separe, Starlette applique cette middleware aussi bien aux
requetes HTTP classiques qu'aux connexions WebSocket.
"""
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from ..database import get_session, engine
from ..models import CercleEtude, MembreCercle, MessageCercle, Filiere, Utilisateur
from ..auth import utilisateur_courant
from ..ws_manager import gestionnaire

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

LONGUEUR_MAX_MESSAGE = 2000


def _est_membre(session: Session, cercle_id: int, utilisateur_id: int) -> bool:
    return session.exec(
        select(MembreCercle).where(
            MembreCercle.cercle_id == cercle_id,
            MembreCercle.utilisateur_id == utilisateur_id,
        )
    ).first() is not None


@router.get("/cercles")
def liste_cercles(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    cercles = session.exec(select(CercleEtude).order_by(CercleEtude.date_creation.desc())).all()
    filieres = session.exec(select(Filiere)).all()

    cercles_avec_info = []
    for cercle in cercles:
        nb_membres = len(
            session.exec(select(MembreCercle).where(MembreCercle.cercle_id == cercle.id)).all()
        )
        cercles_avec_info.append({
            "cercle": cercle,
            "nb_membres": nb_membres,
            "est_membre": _est_membre(session, cercle.id, utilisateur.id) if utilisateur else False,
        })

    return templates.TemplateResponse(
        request,
        "cercles_list.html",
        {
            "cercles_avec_info": cercles_avec_info,
            "filieres": filieres,
            "utilisateur": utilisateur,
        },
    )


@router.post("/cercles/creer")
def creer_cercle(
    request: Request,
    nom: str = Form(...),
    description: Optional[str] = Form(None),
    filiere_id: Optional[int] = Form(None),
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cercle = CercleEtude(
        nom=nom,
        description=description or None,
        filiere_id=filiere_id,
        createur_id=utilisateur.id,
    )
    session.add(cercle)
    session.commit()
    session.refresh(cercle)

    # Le createur rejoint automatiquement son propre cercle.
    session.add(MembreCercle(cercle_id=cercle.id, utilisateur_id=utilisateur.id))
    session.commit()

    return RedirectResponse(f"/cercles/{cercle.id}", status_code=303)


@router.post("/cercles/{cercle_id}/rejoindre")
def rejoindre_cercle(request: Request, cercle_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    if not session.get(CercleEtude, cercle_id):
        return RedirectResponse("/cercles", status_code=303)

    if not _est_membre(session, cercle_id, utilisateur.id):
        session.add(MembreCercle(cercle_id=cercle_id, utilisateur_id=utilisateur.id))
        session.commit()

    return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)


@router.get("/cercles/{cercle_id}")
def salon_cercle(request: Request, cercle_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle:
        return RedirectResponse("/cercles", status_code=303)

    membre = _est_membre(session, cercle_id, utilisateur.id)

    messages = []
    if membre:
        lignes = session.exec(
            select(MessageCercle, Utilisateur)
            .where(MessageCercle.cercle_id == cercle_id)
            .where(MessageCercle.auteur_id == Utilisateur.id)
            .order_by(MessageCercle.date_envoi)
        ).all()
        messages = [
            {
                "auteur": u.nom,
                "auteur_id": u.id,
                "contenu": m.contenu,
                "est_moi": u.id == utilisateur.id,
            }
            for m, u in lignes
        ]

    return templates.TemplateResponse(
        request,
        "cercle_chat.html",
        {
            "cercle": cercle,
            "membre": membre,
            "messages": messages,
            "utilisateur": utilisateur,
        },
    )


@router.websocket("/cercles/{cercle_id}/ws")
async def salon_cercle_websocket(websocket: WebSocket, cercle_id: int):
    user_id = websocket.session.get("user_id")
    if not user_id:
        # Refuse la connexion avant meme le handshake WebSocket si personne
        # n'est connecte (pas de session valide).
        await websocket.close(code=4401)
        return

    with Session(engine) as session:
        utilisateur = session.get(Utilisateur, user_id)
        if not utilisateur or not session.get(CercleEtude, cercle_id) or not _est_membre(session, cercle_id, user_id):
            await websocket.close(code=4403)
            return
        nom_auteur = utilisateur.nom

    await gestionnaire.connecter(cercle_id, websocket)
    try:
        while True:
            donnees_recues = await websocket.receive_json()
            contenu = (donnees_recues.get("contenu") or "").strip()[:LONGUEUR_MAX_MESSAGE]
            if not contenu:
                continue

            with Session(engine) as session:
                message = MessageCercle(cercle_id=cercle_id, auteur_id=user_id, contenu=contenu)
                session.add(message)
                session.commit()

            await gestionnaire.diffuser(cercle_id, {
                "auteur": nom_auteur,
                "auteur_id": user_id,
                "contenu": contenu,
            })
    except WebSocketDisconnect:
        gestionnaire.deconnecter(cercle_id, websocket)
