"""
Protection CSRF par jeton, en complement de SameSite=Lax sur le cookie de
session (voir main.py). SameSite=Lax bloque deja la plupart des attaques
CSRF classiques dans les navigateurs modernes, mais un jeton explicite
est une seconde ligne de defense qui ne depend pas du comportement d'un
navigateur particulier.

Fonctionnement : un jeton aleatoire est genere une fois par session et
stocke server-side (request.session). Il est expose a tous les templates
via jeton_csrf(request) (enregistre comme global Jinja — voir
templating.py), et chaque formulaire POST doit le renvoyer dans un champ
cache "_csrf". verifier_csrf() (dependance FastAPI) compare les deux
valeurs et refuse la requete si elles ne correspondent pas — donc un
formulaire soumis depuis un autre site (qui ne connait pas ce jeton) est
rejete meme s'il a reussi a faire partir la requete.
"""
import secrets

from fastapi import Request, HTTPException


def obtenir_jeton_csrf(request: Request) -> str:
    """Recupere le jeton CSRF de la session courante, en le creant s'il
    n'existe pas encore. A utiliser dans les templates (voir
    templating.py) pour remplir le champ cache de chaque formulaire :
        <input type="hidden" name="_csrf" value="{{ jeton_csrf(request) }}">
    """
    jeton = request.session.get("_csrf_token")
    if not jeton:
        jeton = secrets.token_hex(32)
        request.session["_csrf_token"] = jeton
    return jeton


async def verifier_csrf(request: Request) -> None:
    """Dependance FastAPI a ajouter sur CHAQUE route POST qui modifie un
    etat (Depends(verifier_csrf)). Leve une 403 si le champ cache "_csrf"
    du formulaire soumis ne correspond pas au jeton stocke en session
    (absent, expire, ou requete forgee depuis un autre site)."""
    jeton_attendu = request.session.get("_csrf_token")
    formulaire = await request.form()
    jeton_recu = formulaire.get("_csrf")

    if not jeton_attendu or not jeton_recu or not secrets.compare_digest(str(jeton_attendu), str(jeton_recu)):
        raise HTTPException(
            status_code=403,
            detail="Jeton de securite invalide ou expire. Rechargez la page et reessayez.",
        )
