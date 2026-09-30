"""Worker dedie aux traitements IA lents de Gasy Mahay.

A lancer dans un service Render Background Worker distinct du web :
    python -m app.ai_worker

Le chemin normal est event-driven : le worker attend un ID dans Redis/Render
Key Value avec BRPOP au lieu d'interroger PostgreSQL en boucle. PostgreSQL
reste le journal durable et le filet de securite en cas de panne/perte d'un
message Redis.
"""
import logging
import signal
import time

from . import ai_queue, quiz

logger = logging.getLogger(__name__)

_ARRET = False
TIMEOUT_ATTENTE_REDIS = 15
INTERVALLE_FILET_SECURITE_DB = 30
PAUSE_SANS_REDIS_SECONDES = 1.5


def _arreter(_signal, _frame):
    global _ARRET
    _ARRET = True
    logger.info("Arret demande au worker IA.")


def traiter_tache(tache) -> None:
    if tache.type_tache == ai_queue.TYPE_VERIFICATION_QUIZ:
        quiz.verifier_tentative_en_arriere_plan(
            tache.tentative_quiz_id,
            strategie=tache.strategie_verification,
        )
        return

    raise RuntimeError(f"Type de tache IA inconnu: {tache.type_tache}")


def _obtenir_prochaine_tache(dernier_controle_db: float) -> tuple[object | None, float]:
    """Attend Redis puis utilise PostgreSQL seulement comme filet de securite."""
    maintenant = time.monotonic()

    # En developpement/local sans Redis, on conserve exactement le comportement
    # historique de la file SQL.
    if not ai_queue.redis_configure():
        return ai_queue.prendre_tache(), maintenant

    # Chemin principal : attente bloquante Redis, sans requete PostgreSQL.
    tache_id = ai_queue.attendre_tache(timeout=TIMEOUT_ATTENTE_REDIS)
    if tache_id is not None:
        tache = ai_queue.prendre_tache(tache_id)
        if tache is not None:
            return tache, maintenant

    # Filet de securite volontairement lent : permet de rattraper une tache
    # dont la notification Redis a ete perdue ou si Redis etait temporairement
    # indisponible. Ce n'est pas le chemin nominal.
    if maintenant - dernier_controle_db >= INTERVALLE_FILET_SECURITE_DB:
        return ai_queue.prendre_tache(), maintenant

    return None, dernier_controle_db


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    signal.signal(signal.SIGTERM, _arreter)
    signal.signal(signal.SIGINT, _arreter)

    logger.info(
        "Worker IA demarre: redis_queue=%s cle=%s.",
        ai_queue.redis_configure(),
        ai_queue.CLE_FILE_REDIS,
    )

    dernier_controle_db = 0.0
    while not _ARRET:
        tache = None
        try:
            tache, dernier_controle_db = _obtenir_prochaine_tache(
                dernier_controle_db
            )
            if tache is None:
                if not ai_queue.redis_configure():
                    time.sleep(PAUSE_SANS_REDIS_SECONDES)
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
                # DB/migration indisponible ou erreur transitoire hors prise
                # de tache : ne pas boucler a haute frequence dans les logs.
                time.sleep(5)

    logger.info("Worker IA arrete proprement.")


if __name__ == "__main__":
    main()
