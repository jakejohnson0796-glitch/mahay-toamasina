"""Rate limiting en memoire borne et a fenetre glissante.
Compatible avec une instance unique. Le stockage est borne pour eviter
qu'un attaquant distribue des milliers de cles et provoque une croissance
sans fin du dictionnaire.
"""
import time
from collections import OrderedDict, deque
from threading import Lock
from typing import Deque

MAX_CLES = 10_000
_NETTOYAGE_INTERVALLE = 30.0

_tentatives: "OrderedDict[str, Deque[float]]" = OrderedDict()
_verrou = Lock()
_dernier_nettoyage = 0.0


def _purger_expirees(maintenant: float) -> None:
    for cle, historique in list(_tentatives.items()):
        if not historique or maintenant - historique[-1] >= 3600:
            _tentatives.pop(cle, None)


def limite_depassee(cle: str, max_tentatives: int, fenetre_secondes: int) -> bool:
    if not cle or max_tentatives <= 0 or fenetre_secondes <= 0:
        raise ValueError("Parametres de rate-limit invalides.")

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
