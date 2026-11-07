"""Centre de notifications utilisateur.
Réutilise la table Notification déjà alimentée par les événements du site.
"""
import re

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..auth import utilisateur_courant
from ..csrf import verifier_csrf
from ..database import get_session
from ..institution_access import est_inscrit_cours
from ..models import Devoir, Notification, TypeNotification
from ..templating import templates

router = APIRouter()


_TYPES_NOTIFICATION_COURS = {
    TypeNotification.NOUVEAU_DEVOIR.value,
    TypeNotification.NOTE_PUBLIEE.value,
    TypeNotification.STATUT_PRESENCE.value,
    TypeNotification.RAPPEL_ECHEANCE.value,
    TypeNotification.FICHE_REVISION_PRETE.value,
}


def _cours_id_notification(session: Session, notification: Notification) -> int | None:
    """Résout le cours d'une notification, y compris certains anciens liens."""
    if notification.cours_id is not None:
        return int(notification.cours_id)

    # Les anciennes alertes de devoir et de note contiennent l'identifiant
    # du devoir dans leur URL ; on peut donc reconstituer leur portée.
    destination = (getattr(notification, "url_destination", None) or "").strip()
    correspondance = re.fullmatch(
        r"/classe/devoirs/(\d+)(?:[?#].*)?",
        destination,
    )
    if correspondance:
        devoir = session.get(Devoir, int(correspondance.group(1)))
        return devoir.cours_id if devoir else None
    return None


def _notification_autorisee(
    session: Session,
    utilisateur_id: int,
    notification: Notification,
) -> bool:
    """Les alertes de cours ne survivent pas à la révocation de l'inscription."""
    type_value = getattr(
        notification.type_notification,
        "value",
        notification.type_notification,
    )
    if type_value not in _TYPES_NOTIFICATION_COURS:
        return True

    cours_id = _cours_id_notification(session, notification)
    # Une ancienne alerte pédagogique sans cours identifiable est masquée :
    # mieux vaut ne pas exposer un événement institutionnel non vérifiable.
    return bool(
        cours_id
        and est_inscrit_cours(session, cours_id, utilisateur_id)
    )


def _notification_vue(notification: Notification) -> dict:
    type_value = notification.type_notification.value
    type_labels = {
        "reponse_message": "Réponse à ton message",
        "reponse_thread": "Nouvelle réponse",
        "reaction": "Réaction",
        "mention": "Mention",
        "reponse_feedback": "Réponse à ton avis",
        "inactivite_3_jours": "Reprise après une pause",
        "nouvelle_inscription": "Nouvelle inscription",
        "nouveau_document": "Document à modérer",
        "document_approuve": "Document approuvé",
        "document_rejete": "Document refusé",
        "document_supprime": "Document supprimé",
        "fiche_revision_prete": "Fiche de révision prête",
        "fiche_revision_document_prete": "Fiche de cours disponible",
        "nouveau_devoir": "Nouveau devoir",
        "note_publiee": "Nouvelle note publiée",
        "statut_presence": "Mise à jour de présence",
        "rappel_echeance": "Rappel d’échéance",
    }
    lien = None
    destination = (getattr(notification, "url_destination", None) or "").strip()
    if destination.startswith("/") and not destination.startswith("//") and "\\" not in destination:
        lien = destination
    if lien:
        pass
    elif notification.cercle_id:
        lien = f"/cercles/{notification.cercle_id}"
    elif type_value == "nouvelle_inscription":
        lien = "/admin/utilisateurs"
    elif type_value == "nouveau_document":
        lien = "/moderation"
    elif type_value in {"document_approuve", "document_rejete", "document_supprime"}:
        lien = "/documents"
    elif type_value == "inactivite_3_jours":
        lien = "/dashboard"
    elif type_value == "reponse_feedback":
        lien = "/feedback"
    elif type_value in {"fiche_revision_prete", "fiche_revision_document_prete"}:
        lien = "/mes-revisions"
    return {
        "notification": notification,
        "lien": lien,
        "type_label": type_labels.get(type_value, type_value.replace("_", " ").capitalize()),
    }


@router.get("/notifications")
def page_notifications(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    candidates = session.exec(
        select(Notification)
        .where(Notification.destinataire_id == utilisateur.id)
        .order_by(Notification.date_creation.desc())
        .limit(200)
    ).all()
    notifications = [
        notification for notification in candidates
        if _notification_autorisee(session, utilisateur.id, notification)
    ][:50]

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
    if (
        notification
        and notification.destinataire_id == utilisateur.id
        and _notification_autorisee(session, utilisateur.id, notification)
    ):
        notification.lu = True
        session.add(notification)
        session.commit()
        rappel = request.session.get("notification_inactivite")
        if rappel and rappel.get("notification_id") == notification_id:
            request.session.pop("notification_inactivite", None)

    return RedirectResponse("/notifications", status_code=303)


@router.post("/notifications/{notification_id}/ouvrir")
def ouvrir_notification(
    notification_id: int,
    request: Request,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Ouvre la destination interne d'une notification appartenant à l'utilisateur.

    L'ouverture marque aussi la notification comme lue. La destination est
    calculée côté serveur, jamais acceptée depuis un champ fourni par le client.
    """
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    notification = session.get(Notification, notification_id)
    if (
        not notification
        or notification.destinataire_id != utilisateur.id
        or not _notification_autorisee(session, utilisateur.id, notification)
    ):
        return RedirectResponse("/notifications", status_code=303)

    destination = _notification_vue(notification)["lien"]
    if not destination:
        return RedirectResponse("/notifications", status_code=303)

    notification.lu = True
    session.add(notification)
    session.commit()

    rappel = request.session.get("notification_inactivite")
    if rappel and rappel.get("notification_id") == notification_id:
        request.session.pop("notification_inactivite", None)

    return RedirectResponse(destination, status_code=303)


@router.post("/notifications/lire-toutes")
def marquer_toutes_notifications_lues(
    request: Request,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    candidates = session.exec(
        select(Notification)
        .where(Notification.destinataire_id == utilisateur.id)
        .where(Notification.lu == False)  # noqa: E712
    ).all()
    notifications = [
        notification for notification in candidates
        if _notification_autorisee(session, utilisateur.id, notification)
    ]
    for notification in notifications:
        notification.lu = True
        session.add(notification)
    session.commit()
    request.session.pop("notification_inactivite", None)

    return RedirectResponse("/notifications", status_code=303)
