"""
Protection des fonctionnalites Premium (Quiz IA, cercles d'etude, futur
salon enrichi, documents Premium...).

Suit le meme style que le reste du projet (verification manuelle en debut
de route + redirection explicite) plutot qu'une exception FastAPI, pour
rester coherent avec utilisateur_courant() et les checks admin deja en
place dans documents_router.py / cercles_router.py.
"""
from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from .models import Utilisateur
from . import subscription


def acces_premium_ou_redirection(
    utilisateur: Optional[Utilisateur], session: Session
) -> Optional[RedirectResponse]:
    """A appeler en tout debut d'une route Premium, juste apres avoir
    recupere l'utilisateur courant :

        utilisateur = utilisateur_courant(request, session)
        redirection = acces_premium_ou_redirection(utilisateur, session)
        if redirection:
            return redirection
        # ... suite de la route, acces premium garanti valide ici ...

    Renvoie une RedirectResponse a retourner tel quel si l'acces n'est pas
    valide (vers /connexion si personne n'est connecte, vers /abonnement
    avec un message explicatif sinon), ou None si l'acces Premium est
    valide et que la route peut continuer normalement."""
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    abonnement = subscription.obtenir_abonnement(session, utilisateur.id)
    if abonnement:
        abonnement = subscription.synchroniser_expiration(session, abonnement)

    if not subscription.acces_premium_valide(abonnement):
        return RedirectResponse("/abonnement?premium_requis=1", status_code=303)

    return None
