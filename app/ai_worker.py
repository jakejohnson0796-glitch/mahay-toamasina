"""Worker dedie aux traitements IA lents de Gasy Mahay.

A lancer dans un service Render Background Worker distinct du web :
    python -m app.ai_worker
"""
import logging
import signal
import time

from . import ai_queue, quiz

logger = logging.getLogger(__name__)

_ARRET = False
PAUSE_SECONDES = 1.5


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


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    signal.signal(signal.SIGTERM, _arreter)
    signal.signal(signal.SIGINT, _arreter)

    logger.info("Worker IA demarre.")
    while not _ARRET:
        tache = None
        try:
            tache = ai_queue.prendre_tache()
            if tache is None:
                time.sleep(PAUSE_SECONDES)
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
                # DB/migration indisponible ou erreur transitoire :
                # ralentit le polling pour ne pas remplir les logs.
                time.sleep(10)

    logger.info("Worker IA arrete proprement.")


if __name__ == "__main__":
    main()
