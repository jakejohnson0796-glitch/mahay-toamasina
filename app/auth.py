"""
Authentification simple par session (cookie signe cote serveur).

Pas de JWT ici expres : comme tout est rendu en HTML cote serveur (pas de
frontend JS separe), une session classique est plus simple a maintenir
pour toi et suffit largement pour le MVP.
"""
from typing import Optional
import hashlib

from fastapi import Request, Depends
from passlib.context import CryptContext
from sqlmodel import Session

from .database import get_session
from .models import Utilisateur

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
    """Renvoie l'utilisateur connecte si sa session correspond encore a
    l'etat critique courant du compte."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None

    utilisateur = session.get(Utilisateur, user_id)
    if not utilisateur or utilisateur.banni or not session_utilisateur_valide(request.session, utilisateur):
        request.session.clear()
        return None

    return utilisateur
