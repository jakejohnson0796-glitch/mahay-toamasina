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
    marqueur_cloudflare = request.headers.get("cf-ray")
    if not derriere_render or not marqueur_cloudflare:
        return _ip_valide(adresse_socket) or adresse_socket

    adresse_cloudflare = _ip_valide(request.headers.get("cf-connecting-ip"))
    if adresse_cloudflare:
        return adresse_cloudflare

    # X-Forwarded-For peut contenir des valeurs fournies plus tôt dans la
    # chaîne. Le proxy le plus proche ajoute l'adresse effective à droite ;
    # on parcourt depuis la droite et on ignore toutes les valeurs invalides.
    forwarded = request.headers.get("x-forwarded-for", "")
    for candidat in reversed(forwarded.split(",")):
        adresse = _ip_valide(candidat)
        if adresse:
            return adresse

    return _ip_valide(adresse_socket) or adresse_socket
