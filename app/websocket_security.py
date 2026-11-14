"""Validation stricte de l'origine des connexions WebSocket navigateur."""
from urllib.parse import urlsplit

from fastapi import WebSocket

from .config import parametres


def origine_websocket_autorisee(websocket: WebSocket) -> bool:
    """Refuse les connexions sans Origin ou lancées depuis un autre site.

    Les navigateurs envoient Origin lors de l'ouverture WebSocket. L'hôte
    doit correspondre exactement à Host ; les identifiants, chemins, query
    et fragments sont refusés. En production, HTTPS est obligatoire.
    """
    origine = (websocket.headers.get("origin") or "").strip()
    hote_requete = (websocket.headers.get("host") or "").strip()
    if not origine or not hote_requete or origine.lower() == "null":
        return False
    try:
        analysee = urlsplit(origine)
        # Force aussi la validation du port : urlsplit peut différer
        # l'erreur jusque-là pour des ports mal formés.
        _ = analysee.port
    except ValueError:
        return False

    if (
        analysee.scheme.lower() not in {"http", "https"}
        or not analysee.netloc
        or analysee.username is not None
        or analysee.password is not None
        or analysee.path not in {"", "/"}
        or analysee.query
        or analysee.fragment
    ):
        return False
    if parametres.environnement == "production" and analysee.scheme.lower() != "https":
        return False
    return analysee.netloc.casefold() == hote_requete.casefold()
