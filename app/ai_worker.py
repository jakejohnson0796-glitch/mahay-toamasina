"""Traitement des taches IA.

Le meme module sert de boucle interne au web Render Free et, si un jour un
Background Worker payant est active, peut aussi etre lance comme processus
separe.

Le chemin normal est event-driven : le worker attend un ID dans Redis/Render
Key Value avec BRPOP au lieu d'interroger PostgreSQL en boucle. PostgreSQL
reste le journal durable et le filet de securite en cas de perte d'un message.
"""
import logging
import signal
import threading
import time
from typing import Optional

from . import ai_queue, quiz

logger = logging.getLogger(__name__)

TIMEOUT_ATTENTE_REDIS = 15
INTERVALLE_FILET_SECURITE_DB = 30
PAUSE_SANS_REDIS_SECONDES = 1.5


def traiter_tache(tache) -> None:
    if tache.type_tache == ai_queue.TYPE_VERIFICATION_QUIZ:
        quiz.verifier_tentative_en_arriere_plan(
            tache.tentative_quiz_id,
            strategie=tache.strategie_verification,
        )
        return

    raise RuntimeError(f"Type de tache IA inconnu: {tache.type_tache}")


def _obtenir_prochaine_tache(
    dernier_controle_db: float,
) -> tuple[object | None, float]:
    """Attend Redis puis utilise PostgreSQL seulement comme filet de securite."""
    maintenant = time.monotonic()

    # En developpement/local sans Redis, on conserve le comportement
    # historique de la file SQL.
    if not ai_queue.redis_configure():
        return ai_queue.prendre_tache(), maintenant

    # Chemin principal : attente bloquante Redis, sans requete PostgreSQL.
    tache_id = ai_queue.attendre_tache(timeout=TIMEOUT_ATTENTE_REDIS)
    if tache_id is not None:
        tache = ai_queue.prendre_tache(tache_id)
        if tache is not None:
            return tache, maintenant

    # Filet de securite volontairement lent : rattrape une tache dont la
    # notification Redis a ete perdue ou si Redis etait temporairement
    # indisponible. Ce n'est pas le chemin nominal.
    if maintenant - dernier_controle_db >= INTERVALLE_FILET_SECURITE_DB:
        return ai_queue.prendre_tache(), maintenant

    return None, dernier_controle_db


def boucle_worker(arret: Optional[threading.Event] = None) -> None:
    """Boucle reutilisable en thread interne ou en processus separe."""
    logger.info(
        "Worker IA demarre: redis_queue=%s cle=%s.",
        ai_queue.redis_configure(),
        ai_queue.CLE_FILE_REDIS,
    )

    dernier_controle_db = 0.0
    while arret is None or not arret.is_set():
        tache = None
        try:
            tache, dernier_controle_db = _obtenir_prochaine_tache(
                dernier_controle_db
            )
            if tache is None:
                if arret is not None and arret.is_set():
                    break
                if not ai_queue.redis_configure():
                    if arret is None:
                        time.sleep(PAUSE_SANS_REDIS_SECONDES)
                    else:
                        arret.wait(PAUSE_SANS_REDIS_SECONDES)
                continue

            logger.info(
                "Worker IA traite tache #%s type=%s quiz=%s strategie=%s risque=%s essai=%s.",
                tache.id,
                tache.type_tache,
                tache.tentative_quiz_id,
                tache.strategie_verification,
                tache.score_risque,
                tache.nombre_essais,
            )
            traiter_tache(tache)
            ai_queue.terminer_tache(tache.id)
        except Exception as erreur:
            logger.exception(
                "Erreur worker IA pour tache #%s.",
                getattr(tache, "id", None),
            )
            if tache is not None:
                ai_queue.echouer_tache(tache.id, erreur)
            else:
                if arret is None:
                    time.sleep(5)
                else:
                    arret.wait(5)

    logger.info("Worker IA arrete proprement.")


def main() -> None:
    """Point d'entree pour un processus dedie, utile si l'offre passe au payant."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    arret = threading.Event()

    def _arreter(_signal, _frame):
        arret.set()
        logger.info("Arret demande au worker IA.")

    signal.signal(signal.SIGTERM, _arreter)
    signal.signal(signal.SIGINT, _arreter)

    boucle_worker(arret)


if __name__ == "__main__":
    main()
