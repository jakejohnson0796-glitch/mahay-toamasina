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
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, or_

from ..database import get_session, engine
from ..models import CercleEtude, MembreCercle, MessageCercle, SignalementMessage, Filiere, Utilisateur, RoleUtilisateur
from ..auth import utilisateur_courant
from ..ws_manager import gestionnaire
from ..dependencies import acces_premium_ou_redirection
from ..storage import sauvegarder_fichier, obtenir_url_telechargement, stockage_distant_actif
from .. import subscription

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

LONGUEUR_MAX_MESSAGE = 2000
TAILLE_MAX_PIECE_JOINTE = 10 * 1024 * 1024  # 10 Mo


def _est_membre(session: Session, cercle_id: int, utilisateur_id: int) -> bool:
    return session.exec(
        select(MembreCercle).where(
            MembreCercle.cercle_id == cercle_id,
            MembreCercle.utilisateur_id == utilisateur_id,
        )
    ).first() is not None


def _peut_moderer(cercle: CercleEtude, utilisateur: Optional[Utilisateur]) -> bool:
    """Le createur du cercle et les admins peuvent supprimer un message.
    Volontairement restreint (pas 'tout membre') pour eviter les abus."""
    if not utilisateur:
        return False
    return utilisateur.id == cercle.createur_id or utilisateur.role == RoleUtilisateur.ADMIN


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
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

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
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    if not session.get(CercleEtude, cercle_id):
        return RedirectResponse("/cercles", status_code=303)

    if not _est_membre(session, cercle_id, utilisateur.id):
        session.add(MembreCercle(cercle_id=cercle_id, utilisateur_id=utilisateur.id))
        session.commit()

    return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)


@router.get("/cercles/{cercle_id}")
def salon_cercle(request: Request, cercle_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle:
        return RedirectResponse("/cercles", status_code=303)

    membre = _est_membre(session, cercle_id, utilisateur.id)
    peut_moderer = _peut_moderer(cercle, utilisateur)

    messages = []
    if membre:
        lignes = session.exec(
            select(MessageCercle, Utilisateur)
            .where(MessageCercle.cercle_id == cercle_id)
            .where(MessageCercle.auteur_id == Utilisateur.id)
            .where(MessageCercle.supprime == False)  # noqa: E712 — comparaison SQLModel/SQLAlchemy, pas Python
            .order_by(MessageCercle.date_envoi)
        ).all()
        messages = [
            {
                "id": m.id,
                "auteur": u.nom,
                "auteur_id": u.id,
                "contenu": m.contenu,
                "piece_jointe_chemin": m.piece_jointe_chemin,
                "piece_jointe_nom": m.piece_jointe_nom,
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
            "peut_moderer": peut_moderer,
        },
    )


@router.post("/cercles/{cercle_id}/message-fichier")
async def envoyer_fichier(
    request: Request,
    cercle_id: int,
    fichier: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Partage d'un PDF dans le salon. Passe par une route HTTP classique
    (pas le WebSocket) car un upload de fichier binaire ne s'y prete pas
    bien ; le message resultant est ensuite diffuse en temps reel aux
    membres connectes exactement comme un message texte."""
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle or not _est_membre(session, cercle_id, utilisateur.id):
        return RedirectResponse("/cercles", status_code=303)

    if not fichier.filename or not fichier.filename.lower().endswith(".pdf"):
        return RedirectResponse(f"/cercles/{cercle_id}?erreur=pdf_uniquement", status_code=303)

    reference = f"cercle_{cercle_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    chemin_stocke = sauvegarder_fichier(fichier, reference)

    message = MessageCercle(
        cercle_id=cercle_id,
        auteur_id=utilisateur.id,
        contenu="",
        piece_jointe_chemin=chemin_stocke,
        piece_jointe_nom=fichier.filename,
    )
    session.add(message)
    session.commit()
    session.refresh(message)

    await gestionnaire.diffuser(cercle_id, {
        "type": "message",
        "id": message.id,
        "auteur": utilisateur.nom,
        "auteur_id": utilisateur.id,
        "contenu": "",
        "piece_jointe_nom": fichier.filename,
        "piece_jointe_url": f"/cercles/{cercle_id}/messages/{message.id}/piece-jointe",
    })

    return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)


@router.get("/cercles/{cercle_id}/messages/{message_id}/piece-jointe")
def telecharger_piece_jointe(request: Request, cercle_id: int, message_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or not _est_membre(session, cercle_id, utilisateur.id):
        return RedirectResponse("/connexion", status_code=303)

    message = session.get(MessageCercle, message_id)
    if not message or message.cercle_id != cercle_id or not message.piece_jointe_chemin or message.supprime:
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    if stockage_distant_actif():
        return RedirectResponse(obtenir_url_telechargement(message.piece_jointe_chemin))
    return FileResponse(message.piece_jointe_chemin, filename=message.piece_jointe_nom or "document.pdf")


@router.post("/cercles/{cercle_id}/messages/{message_id}/supprimer")
async def supprimer_message(request: Request, cercle_id: int, message_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cercle = session.get(CercleEtude, cercle_id)
    message = session.get(MessageCercle, message_id)
    if not cercle or not message or message.cercle_id != cercle_id:
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    if not _peut_moderer(cercle, utilisateur):
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    message.supprime = True
    session.add(message)
    session.commit()

    await gestionnaire.diffuser(cercle_id, {"type": "suppression", "id": message.id})

    return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)


@router.post("/cercles/{cercle_id}/messages/{message_id}/signaler")
def signaler_message(
    request: Request,
    cercle_id: int,
    message_id: int,
    motif: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    message = session.get(MessageCercle, message_id)
    if not message or message.cercle_id != cercle_id or not _est_membre(session, cercle_id, utilisateur.id):
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    # Evite les doublons : un signalement non-traite deja existant de ce
    # meme utilisateur sur ce meme message n'est pas duplique.
    deja_signale = session.exec(
        select(SignalementMessage).where(
            SignalementMessage.message_id == message_id,
            SignalementMessage.signale_par_id == utilisateur.id,
            SignalementMessage.traite == False,  # noqa: E712
        )
    ).first()
    if not deja_signale:
        session.add(SignalementMessage(message_id=message_id, signale_par_id=utilisateur.id, motif=motif))
        session.commit()

    return RedirectResponse(f"/cercles/{cercle_id}?signale=1", status_code=303)


@router.get("/cercles/{cercle_id}/recherche")
def rechercher_messages(request: Request, cercle_id: int, q: str = "", session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle or not _est_membre(session, cercle_id, utilisateur.id):
        return RedirectResponse("/cercles", status_code=303)

    resultats = []
    terme = q.strip()
    if terme:
        lignes = session.exec(
            select(MessageCercle, Utilisateur)
            .where(MessageCercle.cercle_id == cercle_id)
            .where(MessageCercle.auteur_id == Utilisateur.id)
            .where(MessageCercle.supprime == False)  # noqa: E712
            .where(MessageCercle.contenu.ilike(f"%{terme}%"))
            .order_by(MessageCercle.date_envoi.desc())
        ).all()
        resultats = [{"auteur": u.nom, "contenu": m.contenu, "date_envoi": m.date_envoi} for m, u in lignes]

    return templates.TemplateResponse(
        request,
        "cercle_recherche.html",
        {"cercle": cercle, "utilisateur": utilisateur, "terme": terme, "resultats": resultats},
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

        abonnement = subscription.obtenir_abonnement(session, user_id)
        if abonnement:
            abonnement = subscription.synchroniser_expiration(session, abonnement)
        if not subscription.acces_premium_valide(abonnement):
            # 4402, en echo au code HTTP 402 Payment Required : pas de
            # redirection possible en WebSocket, donc on ferme simplement
            # la connexion. La page /cercles/{id} (HTTP) bloque deja
            # l'affichage du salon avant meme d'essayer d'ouvrir ce socket.
            await websocket.close(code=4402)
            return

        nom_auteur = utilisateur.nom

    await gestionnaire.connecter(cercle_id, websocket, user_id, nom_auteur)
    await gestionnaire.diffuser_presence(cercle_id)
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
                session.refresh(message)

            await gestionnaire.diffuser(cercle_id, {
                "type": "message",
                "id": message.id,
                "auteur": nom_auteur,
                "auteur_id": user_id,
                "contenu": contenu,
            })
    except WebSocketDisconnect:
        gestionnaire.deconnecter(cercle_id, websocket)
        await gestionnaire.diffuser_presence(cercle_id)
