"""
Limitation de debit minimale, en memoire, pour se proteger des attaques
par force brute sur la connexion et de la creation automatisee massive
de comptes (voir auth_router.py).

Convient a un deploiement mono-instance (ex: Render plan gratuit, qui ne
fait tourner qu'un seul worker). Si un jour plusieurs instances tournent
en parallele derriere un load-balancer, ce compteur en memoire ne sera
plus partage entre elles et la limite deviendra proportionnellement plus
laxiste — il faudrait alors passer sur un stockage partage (Redis, ou une
table Postgres dediee). Pour la taille actuelle du projet, c'est un
compromis raisonnable qui evite d'ajouter une dependance externe.
"""
import time
from collections import defaultdict
from threading import Lock

_tentatives: dict[str, list[float]] = defaultdict(list)
_verrou = Lock()


def limite_depassee(cle: str, max_tentatives: int, fenetre_secondes: int) -> bool:
    """Renvoie True si `cle` (ex: "connexion:ip:1.2.3.4") a deja
    enregistre au moins max_tentatives appels au cours des
    fenetre_secondes dernieres secondes (fenetre glissante).

    Enregistre aussi l'appel courant dans tous les cas, pour que les
    tentatives bloquees comptent elles aussi (sinon un attaquant qui
    reessaie sans relache resterait juste sous le seuil indefiniment)."""
    maintenant = time.monotonic()
    with _verrou:
        historique = _tentatives[cle]
        historique[:] = [t for t in historique if maintenant - t < fenetre_secondes]
        deja_trop = len(historique) >= max_tentatives
        historique.append(maintenant)
        return deja_trop
