"""Rate limiting glissant, partagé entre les instances via Redis.

REDIS_URL est déjà fourni par Render Key Value. Chaque clé est hachée avant
d'être envoyée à Redis et chaque compteur expire automatiquement. Si Redis
est momentanément indisponible, un repli mémoire borné préserve le service ;
ce repli n'a pas la garantie distribuée du compteur Redis.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import time
from collections import OrderedDict, deque
from threading import Lock
from typing import Deque, Optional

from redis import Redis

from .config import parametres

MAX_CLES = 10_000
_NETTOYAGE_INTERVALLE = 30.0
_TTL_INDEX_MS = 3_660_000

_tentatives: "OrderedDict[str, Deque[float]]" = OrderedDict()
_verrou = Lock()
_verrou_journal = Lock()
_dernier_nettoyage = 0.0
_dernier_avertissement_redis = 0.0
_client_redis: Optional[Redis] = None
_url_client_redis = ""

_JOURNAL = logging.getLogger("mahay.security.rate_limit")

_SCRIPT_REDIS = """
local rate_key = KEYS[1]
local index_key = KEYS[2]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local maximum = tonumber(ARGV[3])
local member = ARGV[4]
local maximum_keys = tonumber(ARGV[5])

redis.call('ZREMRANGEBYSCORE', rate_key, '-inf', now_ms - window_ms)
redis.call('ZREMRANGEBYSCORE', index_key, '-inf', now_ms)

local count = redis.call('ZCARD', rate_key)
if count >= maximum then
    redis.call('PEXPIRE', rate_key, window_ms)
    redis.call('ZADD', index_key, now_ms + window_ms, rate_key)
    redis.call('PEXPIRE', index_key, window_ms + 60000)
    return 1
end

redis.call('ZADD', rate_key, now_ms, member)
redis.call('PEXPIRE', rate_key, window_ms)
redis.call('ZADD', index_key, now_ms + window_ms, rate_key)

if redis.call('ZCARD', index_key) > maximum_keys then
    local oldest = redis.call('ZRANGE', index_key, 0, 0)
    if oldest[1] then
        redis.call('DEL', oldest[1])
        redis.call('ZREM', index_key, oldest[1])
    end
end

redis.call('PEXPIRE', index_key, window_ms + 60000)
return 0
"""


def _obtenir_client_redis() -> Optional[Redis]:
    """Construit paresseusement un client Redis avec des délais courts."""
    global _client_redis, _url_client_redis
    url = (parametres.redis_url or "").strip()
    if not url:
        return None

    if _client_redis is None or _url_client_redis != url:
        _client_redis = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
            health_check_interval=30,
        )
        _url_client_redis = url
    return _client_redis


def _noter_indisponibilite_redis(erreur: Exception) -> None:
    """Journalise une panne Redis au plus une fois par minute, sans secret."""
    global _dernier_avertissement_redis
    maintenant = time.monotonic()
    with _verrou_journal:
        if maintenant - _dernier_avertissement_redis >= 60:
            _JOURNAL.warning(
                "Rate-limit Redis indisponible ; repli mémoire temporaire (%s).",
                type(erreur).__name__,
            )
            _dernier_avertissement_redis = maintenant


def _limite_depassee_redis(
    client: Redis,
    cle: str,
    max_tentatives: int,
    fenetre_secondes: int,
) -> bool:
    """Exécute atomiquement le compteur glissant et son index borné."""
    empreinte = hashlib.sha256(cle.encode("utf-8")).hexdigest()
    maintenant_ms = time.time_ns() // 1_000_000
    rate_key = f"mahay:security:rate:v1:{empreinte}"
    index_key = "mahay:security:rate:v1:index"
    membre = f"{maintenant_ms}:{secrets.token_hex(12)}"

    resultat = client.eval(
        _SCRIPT_REDIS,
        2,
        rate_key,
        index_key,
        maintenant_ms,
        fenetre_secondes * 1000,
        max_tentatives,
        membre,
        MAX_CLES,
    )
    return bool(int(resultat))


def _purger_expirees(maintenant: float) -> None:
    for cle, historique in list(_tentatives.items()):
        if not historique or maintenant - historique[-1] >= 3600:
            _tentatives.pop(cle, None)


def _limite_depassee_memoire(cle: str, max_tentatives: int, fenetre_secondes: int) -> bool:
    global _dernier_nettoyage
    maintenant = time.monotonic()
    with _verrou:
        if maintenant - _dernier_nettoyage >= _NETTOYAGE_INTERVALLE:
            _purger_expirees(maintenant)
            _dernier_nettoyage = maintenant

        historique = _tentatives.get(cle)
        if historique is None:
            historique = deque()
            _tentatives[cle] = historique
        else:
            _tentatives.move_to_end(cle)

        seuil = maintenant - fenetre_secondes
        while historique and historique[0] <= seuil:
            historique.popleft()

        deja_trop = len(historique) >= max_tentatives
        historique.append(maintenant)

        while len(_tentatives) > MAX_CLES:
            _tentatives.popitem(last=False)

        return deja_trop


def limite_depassee(cle: str, max_tentatives: int, fenetre_secondes: int) -> bool:
    """Renvoie True lorsque la limite glissante est dépassée.

    Avec REDIS_URL, la décision est atomique et commune aux processus. En cas
    de panne Redis, le service continue avec un stockage local borné.
    """
    if not cle or max_tentatives <= 0 or fenetre_secondes <= 0:
        raise ValueError("Parametres de rate-limit invalides.")

    try:
        client = _obtenir_client_redis()
        if client is not None:
            return _limite_depassee_redis(client, cle, max_tentatives, fenetre_secondes)
    except Exception as erreur:
        _noter_indisponibilite_redis(erreur)

    return _limite_depassee_memoire(cle, max_tentatives, fenetre_secondes)
