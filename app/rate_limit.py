"""Rate limiting avec backend Redis partage si REDIS_URL est configure.
Fallback memoire borne pour le developpement/tests et en cas de panne Redis.
"""
import time
from collections import OrderedDict, deque
from threading import Lock
from typing import Deque, Optional
import redis

from .config import parametres

MAX_CLES = 10_000
_NETTOYAGE_INTERVALLE = 30.0
_tentatives: "OrderedDict[str, Deque[float]]" = OrderedDict()
_verrou = Lock()
_dernier_nettoyage = 0.0
_client_redis: Optional[redis.Redis] = None

_SCRIPT_RATE_LIMIT = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return n
"""


def _redis_client() -> Optional[redis.Redis]:
    global _client_redis
    if not parametres.redis_url:
        return None
    if _client_redis is None:
        _client_redis = redis.Redis.from_url(
            parametres.redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
            health_check_interval=30,
        )
    return _client_redis


def _limite_redis(cle: str, max_tentatives: int, fenetre_secondes: int) -> Optional[bool]:
    client = _redis_client()
    if client is None:
        return None
    try:
        n = int(client.eval(_SCRIPT_RATE_LIMIT, 1, f"mahay:rate:{cle}", fenetre_secondes))
        return n > max_tentatives
    except redis.RedisError:
        return None


def _purger_expirees(maintenant: float) -> None:
    for cle, historique in list(_tentatives.items()):
        if not historique or maintenant - historique[-1] >= 3600:
            _tentatives.pop(cle, None)


def _limite_locale(cle: str, max_tentatives: int, fenetre_secondes: int) -> bool:
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
    if not cle or max_tentatives <= 0 or fenetre_secondes <= 0:
        raise ValueError("Parametres de rate-limit invalides.")
    resultat = _limite_redis(cle, max_tentatives, fenetre_secondes)
    if resultat is not None:
        return resultat
    return _limite_locale(cle, max_tentatives, fenetre_secondes)
