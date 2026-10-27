"""Identification de l'adresse client pour les limites anti-abus.

Sur Render, le socket pointe vers un proxy. On n'utilise les en-têtes
Cloudflare/forwarded que lorsque le marqueur de proxy Cloudflare est présent,
et on valide chaque valeur comme adresse IP avant de s'en servir.
"""
from __future__ import annotations

import ipaddress
import os
from typing import Optional

from starlette.requests import Request


def _ip_valide(valeur: Optional[str]) -> Optional[str]:
    if not valeur:
        return None
    try:
        return str(ipaddress.ip_address(valeur.strip()))
    except ValueError:
        return None


def adresse_ip_client(request: Request) -> str:
    """Renvoie l'IP client fiable pour le rate limiting, avec repli prudent."""
    adresse_socket = request.client.host if request.client else "inconnu"

    # Hors Render, ou sans preuve que la requête est passée par Cloudflare,
    # ne jamais faire confiance à des en-têtes que le client peut forger.
    derriere_render = os.getenv("RENDER", "").strip().lower() == "true"
    entetes = getattr(request, "headers", {})
    marqueur_cloudflare = entetes.get("cf-ray")
    if not derriere_render or not marqueur_cloudflare:
        return _ip_valide(adresse_socket) or adresse_socket

    adresse_cloudflare = _ip_valide(entetes.get("cf-connecting-ip"))
    if adresse_cloudflare:
        return adresse_cloudflare

    # Ne pas retomber sur X-Forwarded-For : ce champ peut contenir une
    # valeur fournie par le visiteur. Si l'IP canonique manque, préférer
    # l'adresse socket (éventuellement le proxy) plutôt que faire confiance
    # à une identité IP contrôlée par le client.
    return _ip_valide(adresse_socket) or adresse_socket
