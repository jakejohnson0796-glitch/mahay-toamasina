"""Limites strictes du corps HTTP avant le parsing des formulaires.

Les limites incluent les octets multipart et s'appliquent même lorsque
Content-Length est absent ou mensonger. Les limites par route préservent
les dépôts légitimes tout en bornant le coût d'une requête.
"""
from __future__ import annotations

from typing import Any

MIB = 1024 * 1024
DEFAULT_MAX_BODY_SIZE = 2 * MIB
SINGLE_DOCUMENT_BODY_LIMIT = 21 * MIB  # 20 MiB de fichier + marge multipart
MULTIPLE_DOCUMENT_BODY_LIMIT = 102 * MIB  # jusqu'à 5 fichiers de 20 MiB + marge
AVATAR_BODY_LIMIT = 6 * MIB  # 5 MiB de photo + marge


def limite_corps_requete(method: str, path: str, default_limit: int = DEFAULT_MAX_BODY_SIZE) -> int:
    """Retourne une limite du corps HTTP fondée sur la route, jamais sur l'en-tête client."""
    if method.upper() not in {"POST", "PUT", "PATCH"}:
        return default_limit
    if path == "/admin/inscriptions-institutionnelles/importer":
        return 6 * MIB  # CSV/XLSX de préinscription + marge multipart
    if path == "/documents/upload-multiple":
        return MULTIPLE_DOCUMENT_BODY_LIMIT
    if path in {"/documents/upload", "/documents/detect"}:
        return SINGLE_DOCUMENT_BODY_LIMIT
    if path == "/profil/photo":
        return AVATAR_BODY_LIMIT
    # Les devoirs acceptent un fichier de document, pas une charge arbitraire.
    morceaux = path.strip("/").split("/")
    if (
        len(morceaux) == 4
        and morceaux[0] == "classe"
        and morceaux[1] == "devoirs"
        and morceaux[2].isdigit()
        and morceaux[3] == "rendre"
    ):
        return SINGLE_DOCUMENT_BODY_LIMIT
    return default_limit


class RequestSizeLimitMiddleware:
    """Middleware ASGI qui rejette les corps surdimensionnés avant le handler."""

    def __init__(self, app: Any, default_max_body_size: int = DEFAULT_MAX_BODY_SIZE) -> None:
        self.app = app
        if default_max_body_size < 1:
            raise ValueError("La limite de corps HTTP doit être positive.")
        self.default_max_body_size = default_max_body_size

    @staticmethod
    async def _envoyer_413(scope: dict, send: Any) -> None:
        corps = b"Request body too large."
        entetes = [
            (b"content-type", b"text/plain; charset=utf-8"),
            (b"content-length", str(len(corps)).encode("ascii")),
            (b"cache-control", b"no-store"),
            (b"x-content-type-options", b"nosniff"),
        ]
        await send({"type": "http.response.start", "status": 413, "headers": entetes})
        await send({"type": "http.response.body", "body": corps, "more_body": False})

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        limit = limite_corps_requete(
            scope.get("method", "GET"),
            scope.get("path", "/"),
            self.default_max_body_size,
        )
        longueur_annoncee = None
        for nom, valeur in scope.get("headers", []):
            if nom.lower() == b"content-length":
                try:
                    longueur_annoncee = int(valeur.decode("ascii").strip())
                except (ValueError, UnicodeDecodeError):
                    longueur_annoncee = None
                break

        # Rejeter tôt les gros corps usuels, avant le parsing multipart.
        if longueur_annoncee is not None and longueur_annoncee > limit:
            await self._envoyer_413(scope, send)
            return

        total_recu = 0
        corps_trop_grand = False
        reponse_commencee = False
        reponse_413_envoyee = False

        async def recevoir_borne() -> dict:
            nonlocal total_recu, corps_trop_grand
            if corps_trop_grand:
                return {"type": "http.request", "body": b"", "more_body": False}
            message = await receive()
            if message.get("type") == "http.request":
                total_recu += len(message.get("body", b""))
                if total_recu > limit:
                    corps_trop_grand = True
                    # Ne transmet pas le fragment qui franchit la limite et
                    # ne lit aucun autre fragment du corps client.
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        async def envoyer_borne(message: dict) -> None:
            nonlocal reponse_commencee, reponse_413_envoyee
            if message.get("type") == "http.response.start":
                reponse_commencee = True
                if corps_trop_grand and not reponse_413_envoyee:
                    reponse_413_envoyee = True
                    await self._envoyer_413(scope, send)
                    return
            if reponse_413_envoyee:
                return
            await send(message)

        try:
            await self.app(scope, recevoir_borne, envoyer_borne)
        except Exception:
            if corps_trop_grand:
                if not reponse_commencee and not reponse_413_envoyee:
                    await self._envoyer_413(scope, send)
                return
            raise

        if corps_trop_grand and not reponse_commencee and not reponse_413_envoyee:
            await self._envoyer_413(scope, send)
