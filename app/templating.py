"""
Instance Jinja2Templates PARTAGEE par tout le projet, a importer partout
(from ..templating import templates) plutot que d'en creer une par
router comme avant. Necessaire pour que jeton_csrf() (voir csrf.py) soit
disponible dans absolument tous les templates, quel que soit le router
qui les rend — une instance par router aurait exige d'enregistrer le
global separement dans chacune, avec le risque d'en oublier une.
"""
from pathlib import Path

from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from .csrf import obtenir_jeton_csrf

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["jeton_csrf"] = obtenir_jeton_csrf


def _profil_academique_a_actualiser(request) -> bool:
    """Global Jinja (meme principe que jeton_csrf ci-dessus) : vrai si
    l'utilisateur connecte est un(e) etudiant(e) dont le profil
    academique a besoin d'etre actualise (§21-22 du brief refonte
    academique nationale — statut PROFILE_ACADEMIC_UPDATE_REQUIRED).

    Enregistre ici plutot que passe explicitement dans le contexte de
    chaque route : la notification doit pouvoir s'afficher dans
    base.html sur N'IMPORTE QUELLE page (§22 : "des qu'un ancien
    utilisateur se connecte"), et la plupart des ~20 routes existantes
    ne passent pas toutes systematiquement `utilisateur` a leur
    template. Ouvre sa propre session DB courte et isolee, le temps de
    cette seule verification — meme logique que jeton_csrf() qui lit
    request.session independamment de la route appelante.

    Import de .database et .models fait ICI (pas en haut du fichier)
    pour eviter tout risque d'import circulaire : ce module est importe
    tres tot par de nombreux routers, avant que database/models n'aient
    forcement fini de s'initialiser dans tous les contextes.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return False

    from .database import engine
    from .models import Utilisateur
    from . import referentiel_academique

    with Session(engine) as session:
        utilisateur = session.get(Utilisateur, user_id)
        if not utilisateur:
            return False
        return referentiel_academique.profil_academique_incomplet(utilisateur, session)


templates.env.globals["profil_academique_a_actualiser"] = _profil_academique_a_actualiser
