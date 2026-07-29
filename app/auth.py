"""
Authentification simple par session (cookie signe cote serveur).

Pas de JWT ici expres : comme tout est rendu en HTML cote serveur (pas de
frontend JS separe), une session classique est plus simple a maintenir
pour toi et suffit largement pour le MVP.
"""
from typing import Optional

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


def utilisateur_courant(request: Request, session: Session = Depends(get_session)) -> Optional[Utilisateur]:
    """Renvoie l'utilisateur connecte via la session, ou None si personne
    n'est connecte. Chaque route decide elle-meme quoi faire de ce None
    (rediriger vers /connexion, ou juste afficher moins d'options)."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return session.get(Utilisateur, user_id)
