"""Centre de notifications utilisateur.
Réutilise la table Notification déjà alimentée par les événements du site.
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..auth import utilisateur_courant
from ..csrf import verifier_csrf
from ..database import get_session
from ..models import Notification
from ..templating import templates

router = APIRouter()


def _notification_vue(notification: Notification) -> dict:
    lien = None
    if notification.cercle_id:
        lien = f"/cercles/{notification.cercle_id}"
    elif notification.type_notification.value == "nouvelle_inscription":
        lien = "/admin/utilisateurs"
    return {"notification": notification, "lien": lien}


@router.get("/notifications")
def page_notifications(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    notifications = session.exec(
        select(Notification)
        .where(Notification.destinataire_id == utilisateur.id)
        .order_by(Notification.date_creation.desc())
        .limit(50)
    ).all()

    return templates.TemplateResponse(
        request,
        "notifications.html",
        {
            "utilisateur": utilisateur,
            "notifications": [_notification_vue(n) for n in notifications],
            "nb_notifications_non_lues": sum(1 for n in notifications if not n.lu),
        },
    )


@router.post("/notifications/{notification_id}/lire")
def marquer_notification_lue(
    notification_id: int,
    request: Request,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    notification = session.get(Notification, notification_id)
    if notification and notification.destinataire_id == utilisateur.id:
        notification.lu = True
        session.add(notification)
        session.commit()
        rappel = request.session.get("notification_inactivite")
        if rappel and rappel.get("notification_id") == notification_id:
            request.session.pop("notification_inactivite", None)

    return RedirectResponse("/notifications", status_code=303)


@router.post("/notifications/lire-toutes")
def marquer_toutes_notifications_lues(
    request: Request,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    notifications = session.exec(
        select(Notification)
        .where(Notification.destinataire_id == utilisateur.id)
        .where(Notification.lu == False)  # noqa: E712
    ).all()
    for notification in notifications:
        notification.lu = True
        session.add(notification)
    session.commit()
    request.session.pop("notification_inactivite", None)

    return RedirectResponse("/notifications", status_code=303)
