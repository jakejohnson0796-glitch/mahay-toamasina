"""File persistante des traitements IA hors requete HTTP.

Le web service ne fait qu'inscrire une tache en base. Un background worker
Render distinct la recupere, l'exécute et gere les retries. Cela évite que les
appels Qwen/Gemini/GPT-OSS monopolisent le worker HTTP.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from .database import engine
from .models import StatutTacheIA, TacheIA, TentativeQuiz
from . import ai_memory, ai_risk

logger = logging.getLogger(__name__)

TYPE_VERIFICATION_QUIZ = "verification_quiz"
DELAIS_REESSAI = (5, 15, 30, 60)
MAX_ESSAIS = 5


def planifier_verification_quiz(tentative_id: int) -> Optional[int]:
    """Ajoute une verification quiz idempotente a la file."""
    maintenant = datetime.utcnow()
    try:
        with Session(engine) as session:
            existante = session.exec(
                select(TacheIA)
                .where(
                    TacheIA.type_tache == TYPE_VERIFICATION_QUIZ,
                    TacheIA.tentative_quiz_id == tentative_id,
                    TacheIA.statut.in_(
                        [
                            StatutTacheIA.EN_ATTENTE,
                            StatutTacheIA.EN_COURS,
                            StatutTacheIA.TERMINEE,
                        ]
                    ),
                )
                .limit(1)
            ).first()
            if existante:
                return existante.id

            tentative = session.get(TentativeQuiz, tentative_id)
            if not tentative:
                return None

            try:
                questions = json.loads(tentative.questions_json)
            except (TypeError, ValueError):
                questions = []

            risque = ai_risk.analyser_risque(
                questions,
                matiere=tentative.matiere,
                niveau=tentative.niveau,
                difficulte=tentative.difficulte,
                signaux_recurrents=ai_memory.nb_signaux_recurrents(
                    type_interaction="quiz",
                    matiere=tentative.matiere,
                    niveau=tentative.niveau,
                ),
            )

            tache = TacheIA(
                type_tache=TYPE_VERIFICATION_QUIZ,
                tentative_quiz_id=tentative_id,
                statut=StatutTacheIA.EN_ATTENTE,
                strategie_verification=risque["strategie"],
                score_risque=risque["score"],
                disponible_le=maintenant,
                date_creation=maintenant,
            )
            session.add(tache)
            session.commit()
            session.refresh(tache)
            logger.info(
                "Tache IA %s planifiee pour quiz #%s: strategie=%s score_risque=%s raisons=%s.",
                tache.id,
                tentative_id,
                tache.strategie_verification,
                tache.score_risque,
                risque["raisons"],
            )
            return tache.id
    except Exception:
        logger.exception(
            "Impossible de planifier la verification IA du quiz #%s.",
            tentative_id,
        )
        return None


def _verrouiller_tache(session: Session) -> Optional[TacheIA]:
    """Prend une seule tache disponible, sans double execution entre workers."""
    dialecte = session.get_bind().dialect.name
    requete = (
        select(TacheIA)
        .where(
            TacheIA.statut == StatutTacheIA.EN_ATTENTE,
            TacheIA.disponible_le <= datetime.utcnow(),
        )
        .order_by(TacheIA.id)
        .limit(1)
    )
    if dialecte == "postgresql":
        requete = requete.with_for_update(skip_locked=True)

    tache = session.exec(requete).first()
    if not tache:
        return None

    tache.statut = StatutTacheIA.EN_COURS
    tache.nombre_essais += 1
    tache.prise_en_charge_le = datetime.utcnow()
    tache.derniere_erreur = None
    session.add(tache)
    session.commit()
    session.refresh(tache)
    return tache


def prendre_tache() -> Optional[TacheIA]:
    with Session(engine) as session:
        return _verrouiller_tache(session)


def terminer_tache(tache_id: int) -> None:
    with Session(engine) as session:
        tache = session.get(TacheIA, tache_id)
        if not tache:
            return
        tache.statut = StatutTacheIA.TERMINEE
        tache.terminee_le = datetime.utcnow()
        tache.derniere_erreur = None
        session.add(tache)
        session.commit()
        logger.info("Tache IA %s terminee.", tache_id)


def echouer_tache(tache_id: int, erreur: Exception) -> None:
    with Session(engine) as session:
        tache = session.get(TacheIA, tache_id)
        if not tache:
            return

        tache.derniere_erreur = f"{type(erreur).__name__}: {erreur}"[:1000]
        if tache.nombre_essais >= MAX_ESSAIS:
            tache.statut = StatutTacheIA.ECHOUEE
            tache.terminee_le = datetime.utcnow()
            logger.error(
                "Tache IA %s abandonnee apres %s essais: %s",
                tache_id,
                tache.nombre_essais,
                tache.derniere_erreur,
            )
        else:
            index_delai = min(tache.nombre_essais - 1, len(DELAIS_REESSAI) - 1)
            tache.statut = StatutTacheIA.EN_ATTENTE
            tache.disponible_le = datetime.utcnow() + timedelta(
                seconds=DELAIS_REESSAI[index_delai]
            )
            logger.warning(
                "Tache IA %s replanifiee dans %ss apres echec (%s/%s).",
                tache_id,
                DELAIS_REESSAI[index_delai],
                tache.nombre_essais,
                MAX_ESSAIS,
            )

        session.add(tache)
        session.commit()
