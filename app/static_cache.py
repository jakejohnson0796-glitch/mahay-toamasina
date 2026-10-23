"""Cache HTTP des ressources statiques dont l'URL est versionnée.

Les templates ajoutent ?v=<hash-du-fichier>-<commit> aux assets. Une telle URL
change avec le contenu et peut donc être conservée sans revalidation ; les pages
HTML, les URLs statiques non versionnées et /sw.js restent hors de cette règle.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs
from typing import Any, Awaitable, Callable

# Contrat utilisé par version_asset() et par les dépendances vendor épinglées.
_VERSION_IMMUABLE = re.compile(
    r"(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{12}|[0-9]+\\.[0-9]+\\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?)"
)


def _requete_asset_versionne(scope: dict[str, Any]) -> bool:
    if scope.get("type") != "http" or scope.get("method") not in {"GET", "HEAD"}:
        return False
    if not str(scope.get("path", "")).startswith("/static/"):
        return False

    chaine = scope.get("query_string", b"").decode("ascii", "ignore")
    versions = parse_qs(chaine).get("v", ())
    return any(_VERSION_IMMUABLE.fullmatch(version.strip()) for version in versions)


class VersionedStaticAssetCacheMiddleware:
    """Ajoute un cache immuable aux seules réponses réussies d'assets versionnés."""

    def __init__(self, app: Callable[..., Awaitable[None]], max_age: int = 31_536_000) -> None:
        self.app = app
        self.cache_control = f"public, max-age={int(max_age)}, immutable".encode("ascii")

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Awaitable[Any]], send: Callable[..., Awaitable[None]]) -> None:
        if not _requete_asset_versionne(scope):
            await self.app(scope, receive, send)
            return

        async def envoyer_avec_cache(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                statut = int(message.get("status", 0))
                if 200 <= statut < 300 or statut == 304:
                    entetes = [
                        (nom, valeur)
                        for nom, valeur in message.get("headers", [])
                        if nom.lower() != b"cache-control"
                    ]
                    entetes.append((b"cache-control", self.cache_control))
                    message = dict(message)
                    message["headers"] = entetes
            await send(message)

        await self.app(scope, receive, envoyer_avec_cache)
