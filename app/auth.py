"""
Authentification simple par session (cookie signe cote serveur).

Pas de JWT ici expres : comme tout est rendu en HTML cote serveur (pas de
frontend JS separe), une session classique est plus simple a maintenir
pour toi et suffit largement pour le MVP.
"""
from typing import Optional
from datetime import datetime, timedelta
import hashlib

from fastapi import Request, Depends
from passlib.context import CryptContext
from sqlmodel import Session, select

from .database import get_session
from .models import Utilisateur, RoleUtilisateur, Notification, TypeNotification

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hacher_mot_de_passe(mot_de_passe: str) -> str:
    return pwd_context.hash(mot_de_passe)


def verifier_mot_de_passe(mot_de_passe: str, hash_stocke: str) -> bool:
    return pwd_context.verify(mot_de_passe, hash_stocke)


def empreinte_session_utilisateur(utilisateur: Utilisateur) -> str:
    """Empreinte non-secrete de l'etat d'authentification critique.

    Elle change apres un changement de mot de passe, de role ou de configuration 2FA.
    Le hash bcrypt n'est jamais stocke directement dans la session."""
    source = "|".join([
        utilisateur.mot_de_passe_hash,
        str(utilisateur.role.value),
        "2fa=1" if utilisateur.totp_active else "2fa=0",
    ])
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def session_utilisateur_valide(session_data: dict, utilisateur: Utilisateur) -> bool:
    return (
        session_data.get("user_id") == utilisateur.id
        and session_data.get("auth_fingerprint") == empreinte_session_utilisateur(utilisateur)
    )


def utilisateur_courant(request: Request, session: Session = Depends(get_session)) -> Optional[Utilisateur]:
    """Renvoie l'utilisateur connecte et rafraichit son activite de facon limitee."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None

    utilisateur = session.get(Utilisateur, user_id)
    if not utilisateur or utilisateur.banni or not session_utilisateur_valide(request.session, utilisateur):
        request.session.clear()
        return None

    enregistrer_activite(utilisateur, session)
    return utilisateur

INTERVALLE_MAJ_ACTIVITE = timedelta(minutes=15)
SEUIL_NOTIFICATION_INACTIVITE = timedelta(days=3)


def jours_inactivite(utilisateur: Utilisateur, maintenant: Optional[datetime] = None) -> int:
    """Nombre de jours complets depuis la derniere activite."""
    if not utilisateur.derniere_activite_le:
        return 0
    maintenant = maintenant or datetime.utcnow()
    return max(0, (maintenant - utilisateur.derniere_activite_le).days)


def enregistrer_activite(
    utilisateur: Utilisateur,
    session: Session,
    *,
    maintenant: Optional[datetime] = None,
    forcer: bool = False,
) -> int:
    maintenant = maintenant or datetime.utcnow()
    if (
        not forcer
        and utilisateur.derniere_activite_le
        and maintenant - utilisateur.derniere_activite_le < INTERVALLE_MAJ_ACTIVITE
    ):
        return jours_inactivite(utilisateur, maintenant)

    jours = jours_inactivite(utilisateur, maintenant)
    utilisateur.derniere_activite_le = maintenant
    session.add(utilisateur)
    session.commit()
    session.refresh(utilisateur)
    return jours


def notifier_nouvelle_inscription_aux_admins(utilisateur: Utilisateur, session: Session) -> int:
    """Cree une notification interne pour chaque administrateur."""
    administrateurs = session.exec(
        select(Utilisateur).where(Utilisateur.role == RoleUtilisateur.ADMIN)
    ).all()
    for administrateur in administrateurs:
        session.add(
            Notification(
                destinataire_id=administrateur.id,
                type_notification=TypeNotification.NOUVELLE_INSCRIPTION,
                contenu=(
                    f"Nouvelle inscription : {utilisateur.nom} "
                    f"(compte cree le {utilisateur.date_creation.strftime('%d/%m/%Y')})."
                ),
                acteur_id=utilisateur.id,
            )
        )
    return len(administrateurs)


def creer_rappel_inactivite_si_necessaire(
    utilisateur: Utilisateur,
    session: Session,
    *,
    maintenant: Optional[datetime] = None,
) -> tuple[int, Optional[int]]:
    maintenant = maintenant or datetime.utcnow()
    jours = jours_inactivite(utilisateur, maintenant)
    notification_id = None

    if jours >= SEUIL_NOTIFICATION_INACTIVITE.days:
        notification = Notification(
            destinataire_id=utilisateur.id,
            type_notification=TypeNotification.INACTIVITE_3_JOURS,
            contenu=(
                f"Bienvenue de retour ! Tu n'as pas utilise Gasy Mahay depuis {jours} "
                f"jour{'s' if jours != 1 else ''}. Reprends ton apprentissage quand tu le souhaites."
            ),
        )
        session.add(notification)
        session.flush()
        notification_id = notification.id

    utilisateur.derniere_activite_le = maintenant
    session.add(utilisateur)
    session.commit()
    session.refresh(utilisateur)
    return jours, notification_id
