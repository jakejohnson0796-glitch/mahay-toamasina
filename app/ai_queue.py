"""File persistante des traitements IA hors requete HTTP.

Le web service ne fait qu'inscrire une tache en base et notifie Redis.
Le worker Render recupere les IDs via une file Redis bloquante ; PostgreSQL
reste la source de verite durable et sert uniquement de filet de securite
si Redis est indisponible ou si une notification a ete perdue.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import redis
from sqlmodel import Session, select

from .config import parametres
from .database import engine
from .models import SessionTuteur, StatutTacheIA, TacheIA, TentativeQuiz
from . import ai_memory, ai_risk

logger = logging.getLogger(__name__)

TYPE_VERIFICATION_QUIZ = "verification_quiz"
TYPE_VERIFICATION_TUTEUR = "verification_tuteur"
DELAIS_REESSAI = (5, 15, 30, 60)
MAX_ESSAIS = 5

# Redis est volontairement un accelerateur de file, pas la source de verite :
# meme si le message Redis disparait, la tache reste durablement en PostgreSQL.
CLE_FILE_REDIS = parametres.ai_queue_redis_key
_TIMEOUT_CONNEXION_REDIS = 2
_TIMEOUT_PRODUCTEUR_REDIS = 1
_TIMEOUT_ATTENTE_REDIS = 15
_TIMEOUT_CONSOMMATEUR_REDIS = _TIMEOUT_ATTENTE_REDIS + 5
_client_producteur_redis: Optional[redis.Redis] = None
_client_consommateur_redis: Optional[redis.Redis] = None


def _creer_client_redis(socket_timeout: float) -> redis.Redis:
    return redis.Redis.from_url(
        parametres.redis_url,
        decode_responses=True,
        socket_connect_timeout=_TIMEOUT_CONNEXION_REDIS,
        socket_timeout=socket_timeout,
        health_check_interval=30,
    )


def _client_producteur() -> Optional[redis.Redis]:
    """Client court pour ne jamais ralentir inutilement les requetes HTTP."""
    global _client_producteur_redis

    if not parametres.redis_url:
        return None

    if _client_producteur_redis is None:
        _client_producteur_redis = _creer_client_redis(_TIMEOUT_PRODUCTEUR_REDIS)
    return _client_producteur_redis


def _client_consommateur() -> Optional[redis.Redis]:
    """Client dedie au BRPOP, avec un timeout superieur au timeout Redis."""
    global _client_consommateur_redis

    if not parametres.redis_url:
        return None

    if _client_consommateur_redis is None:
        _client_consommateur_redis = _creer_client_redis(_TIMEOUT_CONSOMMATEUR_REDIS)
    return _client_consommateur_redis


def _invalider_clients_redis() -> None:
    global _client_producteur_redis, _client_consommateur_redis

    clients = (_client_producteur_redis, _client_consommateur_redis)
    _client_producteur_redis = None
    _client_consommateur_redis = None
    for client in clients:
        if client is None:
            continue
        try:
            client.close()
        except Exception:
            logger.debug("Fermeture du client Redis impossible.", exc_info=True)


def redis_configure() -> bool:
    """Indique si la file Redis est configuree dans l'environnement."""
    return bool(parametres.redis_url)


def notifier_tache(tache_id: int) -> bool:
    """Publie un ID de tache dans Redis.

    Retourne False si Redis n'est pas configure ou temporairement indisponible.
    Dans ce cas, la tache reste quand meme en PostgreSQL et sera recuperable
    par le filet de securite du worker.
    """
    client = _client_producteur()
    if client is None:
        return False

    try:
        profondeur = client.rpush(CLE_FILE_REDIS, str(tache_id))
        print(
            f"[AI QUEUE] Redis RPUSH tache={tache_id} queue={CLE_FILE_REDIS} profondeur={profondeur}.",
            flush=True,
        )
        return True
    except redis.RedisError:
        logger.warning(
            "Notification Redis impossible pour la tache IA #%s; "
            "le fallback PostgreSQL reste actif.",
            tache_id,
            exc_info=True,
        )
        _invalider_clients_redis()
        return False


def attendre_tache(timeout: int = 15) -> Optional[int]:
    """Attend bloquante l'arrivee d'une tache Redis.

    Aucune interrogation PostgreSQL n'est effectuee ici. Un timeout renvoie
    simplement None afin que le worker puisse lancer son controle de securite.
    """
    client = _client_consommateur()
    if client is None:
        return None

    try:
        resultat = client.brpop(CLE_FILE_REDIS, timeout=timeout)
    except redis.RedisError:
        logger.warning(
            "Lecture Redis impossible; le worker basculera temporairement "
            "sur le filet de securite PostgreSQL.",
            exc_info=True,
        )
        _invalider_clients_redis()
        return None

    if not resultat:
        return None

    _cle, valeur = resultat
    print(
        f"[AI QUEUE] Redis BRPOP recu tache={valeur} queue={CLE_FILE_REDIS}.",
        flush=True,
    )
    try:
        return int(valeur)
    except (TypeError, ValueError):
        logger.warning("Message Redis invalide dans %s: %r.", CLE_FILE_REDIS, valeur)
        return None


def longueur_file_redis() -> Optional[int]:
    """Retourne la profondeur Redis, ou None si Redis n'est pas disponible."""
    client = _client_producteur()
    if client is None:
        return None

    try:
        return int(client.llen(CLE_FILE_REDIS))
    except redis.RedisError:
        _invalider_clients_redis()
        return None


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
                # Une tache encore en attente peut avoir perdu sa notification
                # Redis (restart, reseau, etc.). On la repousse sans recreer
                # une ligne SQL, en gardant l'idempotence.
                if existante.statut == StatutTacheIA.EN_ATTENTE:
                    notifier_tache(existante.id)
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

            publiee = notifier_tache(tache.id)
            print(
                f"[AI QUEUE] Tache creee id={tache.id} quiz={tentative_id} "
                f"strategie={tache.strategie_verification} risque={tache.score_risque} "
                f"redis_notifiee={publiee}.",
                flush=True,
            )
            logger.info(
                "Tache IA %s planifiee pour quiz #%s: strategie=%s "
                "score_risque=%s raisons=%s redis_notifiee=%s.",
                tache.id,
                tentative_id,
                tache.strategie_verification,
                tache.score_risque,
                risque["raisons"],
                publiee,
            )
            return tache.id
    except Exception as erreur:
        print(
            f"[AI QUEUE][ERREUR] planification quiz={tentative_id} "
            f"type={type(erreur).__name__} detail={erreur}",
            flush=True,
        )
        logger.exception(
            "Impossible de planifier la verification IA du quiz #%s.",
            tentative_id,
        )
        return None



def planifier_verification_tuteur(session_tuteur_id: int) -> Optional[int]:
    """Ajoute une verification Tuteur durable et idempotente a la file."""
    maintenant = datetime.utcnow()
    try:
        with Session(engine) as session:
            session_tuteur = session.get(SessionTuteur, session_tuteur_id)
            if not session_tuteur:
                return None

            existante = session.exec(
                select(TacheIA)
                .where(
                    TacheIA.type_tache == TYPE_VERIFICATION_TUTEUR,
                    TacheIA.session_tuteur_id == session_tuteur_id,
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
                if existante.statut == StatutTacheIA.EN_ATTENTE:
                    notifier_tache(existante.id)
                return existante.id

            tache = TacheIA(
                type_tache=TYPE_VERIFICATION_TUTEUR,
                tentative_quiz_id=None,
                session_tuteur_id=session_tuteur_id,
                statut=StatutTacheIA.EN_ATTENTE,
                strategie_verification="legere",
                score_risque=0,
                disponible_le=maintenant,
                date_creation=maintenant,
            )
            session.add(tache)
            session.commit()
            session.refresh(tache)

            publiee = notifier_tache(tache.id)
            print(
                f"[AI QUEUE] Tache creee id={tache.id} tuteur={session_tuteur_id} "
                f"strategie={tache.strategie_verification} redis_notifiee={publiee}.",
                flush=True,
            )
            logger.info(
                "Tache IA %s planifiee pour Tuteur #%s: strategie=%s redis_notifiee=%s.",
                tache.id,
                session_tuteur_id,
                tache.strategie_verification,
                publiee,
            )
            return tache.id
    except Exception as erreur:
        print(
            f"[AI QUEUE][ERREUR] planification tuteur={session_tuteur_id} "
            f"type={type(erreur).__name__} detail={erreur}",
            flush=True,
        )
        logger.exception(
            "Impossible de planifier la verification IA du Tuteur #%s.",
            session_tuteur_id,
        )
        return None


def reparer_taches_en_cours_orphelines(
    max_taches: int = 5,
    age_secondes: int = 600,
) -> int:
    """Remet en file les taches dont le worker est mort pendant le traitement."""
    maintenant = datetime.utcnow()
    seuil = maintenant - timedelta(seconds=max(1, age_secondes))

    with Session(engine) as session:
        requete = (
            select(TacheIA)
            .where(
                TacheIA.statut == StatutTacheIA.EN_COURS,
                (TacheIA.prise_en_charge_le.is_(None))
                | (TacheIA.prise_en_charge_le <= seuil),
            )
            .order_by(TacheIA.prise_en_charge_le, TacheIA.id)
            .limit(max(1, max_taches))
        )
        if session.get_bind().dialect.name == "postgresql":
            requete = requete.with_for_update(skip_locked=True)

        taches = session.exec(requete).all()
        if not taches:
            return 0

        ids = []
        for tache in taches:
            tache.statut = StatutTacheIA.EN_ATTENTE
            tache.disponible_le = maintenant
            tache.prise_en_charge_le = None
            tache.derniere_erreur = (
                "Reprise automatique après expiration du lease worker."
            )
            session.add(tache)
            ids.append(tache.id)
        session.commit()

    for tache_id in ids:
        notifier_tache(tache_id)

    logger.warning(
        "Reprise de %s tache(s) IA orpheline(s) après expiration du lease.",
        len(ids),
    )
    return len(ids)


def _verrouiller_tache(
    session: Session,
    tache_id: Optional[int] = None,
) -> Optional[TacheIA]:
    """Prend une tache disponible, sans double execution entre workers.

    Avec un ID venant de Redis, on cible cette tache. Sans ID, on effectue le
    controle de securite PostgreSQL qui recupere la plus ancienne tache encore
    en attente. Ce second chemin est reserve au rattrapage.
    """
    dialecte = session.get_bind().dialect.name
    maintenant = datetime.utcnow()

    requete = select(TacheIA).where(
        TacheIA.statut == StatutTacheIA.EN_ATTENTE,
        TacheIA.disponible_le <= maintenant,
    )
    if tache_id is not None:
        requete = requete.where(TacheIA.id == tache_id)
    else:
        requete = requete.order_by(TacheIA.id)

    requete = requete.limit(1)
    if dialecte == "postgresql":
        requete = requete.with_for_update(skip_locked=True)

    tache = session.exec(requete).first()
    if not tache:
        return None

    tache.statut = StatutTacheIA.EN_COURS
    tache.nombre_essais += 1
    tache.prise_en_charge_le = maintenant
    tache.derniere_erreur = None
    session.add(tache)
    session.commit()
    session.refresh(tache)
    print(
        f"[AI QUEUE] Tache claim id={tache.id} type={tache.type_tache} "
        f"quiz={tache.tentative_quiz_id} tuteur={tache.session_tuteur_id} "
        f"essai={tache.nombre_essais}.",
        flush=True,
    )
    return tache


def prendre_tache(tache_id: Optional[int] = None) -> Optional[TacheIA]:
    with Session(engine) as session:
        return _verrouiller_tache(session, tache_id=tache_id)


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
        print(f"[AI QUEUE] Tache terminee id={tache_id}.", flush=True)
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
        if tache.statut == StatutTacheIA.ECHOUEE:
            print(
                f"[AI QUEUE] Tache abandonnee id={tache_id} apres {tache.nombre_essais} essais.",
                flush=True,
            )
        else:
            print(
                f"[AI QUEUE] Tache replanifiee id={tache_id} essai={tache.nombre_essais} "
                f"disponible_le={tache.disponible_le.isoformat() if tache.disponible_le else None}.",
                flush=True,
            )
