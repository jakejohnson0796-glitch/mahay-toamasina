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

from sqlmodel import Session

from .database import engine
from .models import SessionTuteur
from . import ai_queue, ai_quiz, quiz

logger = logging.getLogger(__name__)

TIMEOUT_ATTENTE_REDIS = 15
INTERVALLE_FILET_SECURITE_DB = 30
PAUSE_SANS_REDIS_SECONDES = 1.5
PAUSE_APRES_FILE_VIDE_SECONDES = 0.5


def traiter_tache(tache) -> None:
    if tache.type_tache == ai_queue.TYPE_VERIFICATION_QUIZ:
        if not tache.tentative_quiz_id:
            raise RuntimeError("Tache de verification quiz sans tentative_quiz_id.")
        quiz.verifier_tentative_en_arriere_plan(
            tache.tentative_quiz_id,
            strategie=tache.strategie_verification,
        )
        return

    if tache.type_tache == ai_queue.TYPE_VERIFICATION_TUTEUR:
        if not tache.session_tuteur_id:
            raise RuntimeError("Tache de verification Tuteur sans session_tuteur_id.")

        ai_quiz.verifier_session_tuteur_en_arriere_plan(
            tache.session_tuteur_id
        )
        with Session(engine) as session:
            session_tuteur = session.get(SessionTuteur, tache.session_tuteur_id)
            if not session_tuteur:
                raise RuntimeError(
                    f"Session Tuteur #{tache.session_tuteur_id} introuvable après traitement."
                )
            if session_tuteur.statut_verification_ia != "terminee":
                raise RuntimeError(
                    session_tuteur.erreur_verification_ia
                    or (
                        f"Verification Tuteur #{tache.session_tuteur_id} "
                        f"terminee avec statut {session_tuteur.statut_verification_ia!r}."
                    )
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
    print(
        f"[AI WORKER] Demarre redis_queue={ai_queue.redis_configure()} "
        f"cle={ai_queue.CLE_FILE_REDIS}.",
        flush=True,
    )
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

                # Le worker ne depend plus d'une BackgroundTask HTTP pour le
                # Tuteur. Les anciennes sessions non encore planifiees sont
                # converties en taches durables par ce filet de securite.
                try:
                    ai_queue.reparer_taches_en_cours_orphelines(
                        max_taches=5,
                        age_secondes=600,
                    )
                    ai_quiz.reparer_verifications_tuteur_en_attente(
                        max_sessions=2,
                        age_minimum_secondes=60,
                        age_en_cours_secondes=600,
                    )
                except Exception:
                    logger.exception("Impossible de reparer la file IA Tuteur.")

                delai = (
                    PAUSE_SANS_REDIS_SECONDES
                    if not ai_queue.redis_configure()
                    else PAUSE_APRES_FILE_VIDE_SECONDES
                )
                if arret is None:
                    time.sleep(delai)
                else:
                    arret.wait(delai)
                continue

            print(
                f"[AI WORKER] Traitement tache={tache.id} type={tache.type_tache} "
                f"quiz={tache.tentative_quiz_id} tuteur={tache.session_tuteur_id} "
                f"strategie={tache.strategie_verification} risque={tache.score_risque} "
                f"essai={tache.nombre_essais}.",
                flush=True,
            )
            logger.info(
                "Worker IA traite tache #%s type=%s quiz=%s tuteur=%s strategie=%s "
                "risque=%s essai=%s.",
                tache.id,
                tache.type_tache,
                tache.tentative_quiz_id,
                tache.session_tuteur_id,
                tache.strategie_verification,
                tache.score_risque,
                tache.nombre_essais,
            )
            traiter_tache(tache)
            ai_queue.terminer_tache(tache.id)
        except Exception as erreur:
            print(
                f"[AI WORKER][ERREUR] tache={getattr(tache, 'id', None)} "
                f"type={type(erreur).__name__} detail={erreur}",
                flush=True,
            )
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

    print("[AI WORKER] Arrete proprement.", flush=True)
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
