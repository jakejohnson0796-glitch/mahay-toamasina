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
from sqlalchemy import or_

from .config import parametres
from .database import engine
from .models import (
    Cours, Document, FicheRevisionCours, FicheRevisionDocument, InscriptionCours,
    Seance, SessionTuteur, StatutDocument, StatutFicheRevisionCours,
    StatutFicheRevisionDocument, StatutSeance, StatutTacheIA, TacheIA,
    TentativeQuiz, TypeDocument,
)
from . import ai_memory, ai_risk

logger = logging.getLogger(__name__)

TYPE_VERIFICATION_QUIZ = "verification_quiz"
TYPE_VERIFICATION_TUTEUR = "verification_tuteur"
TYPE_RESUME_DOCUMENT = "resume_document"
TYPE_FICHE_REVISION_COURS = "fiche_revision_cours"
TYPE_FICHE_REVISION_DOCUMENT = "fiche_revision_document"
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



def planifier_resume_document(document_id: int) -> Optional[int]:
    """Ajoute ou réactive une tâche durable de fiche pédagogique, sans doublon."""
    maintenant = datetime.utcnow()
    try:
        with Session(engine) as session:
            document = session.get(Document, document_id)
            if not document:
                return None
            fiche_fr_prete = bool(
                document.resume_ia
                and document.resume_statut_ia in {"generee", "provisoire", "insuffisante"}
            )
            fiche_mg_finale = bool(
                document.resume_ia_mg
                and document.resume_statut_ia_mg in {"generee", "indisponible"}
            )
            if fiche_fr_prete and fiche_mg_finale:
                return None

            existante = session.exec(
                select(TacheIA)
                .where(
                    TacheIA.type_tache == TYPE_RESUME_DOCUMENT,
                    TacheIA.document_id == document_id,
                )
                .limit(1)
            ).first()

            if existante and existante.statut == StatutTacheIA.EN_COURS:
                if not fiche_fr_prete:
                    document.resume_statut_ia = "en_cours"
                document.resume_statut_ia_mg = "en_cours"
                session.add(document)
                session.commit()
                return existante.id

            if existante and existante.statut == StatutTacheIA.EN_ATTENTE:
                existante.disponible_le = maintenant
                existante.derniere_erreur = None
                if not fiche_fr_prete:
                    document.resume_statut_ia = "en_attente"
                document.resume_statut_ia_mg = "en_attente"
                session.add(existante)
                session.add(document)
                session.commit()
                tache_id = existante.id
            elif existante:
                existante.statut = StatutTacheIA.EN_ATTENTE
                existante.nombre_essais = 0
                existante.disponible_le = maintenant
                existante.prise_en_charge_le = None
                existante.terminee_le = None
                existante.derniere_erreur = None
                if not fiche_fr_prete:
                    document.resume_statut_ia = "en_attente"
                document.resume_statut_ia_mg = "en_attente"
                session.add(existante)
                session.add(document)
                session.commit()
                tache_id = existante.id
            else:
                tache = TacheIA(
                    type_tache=TYPE_RESUME_DOCUMENT,
                    tentative_quiz_id=None,
                    session_tuteur_id=None,
                    document_id=document_id,
                    statut=StatutTacheIA.EN_ATTENTE,
                    strategie_verification="fiche_pedagogique",
                    score_risque=0,
                    disponible_le=maintenant,
                    date_creation=maintenant,
                )
                if not fiche_fr_prete:
                    document.resume_statut_ia = "en_attente"
                document.resume_statut_ia_mg = "en_attente"
                session.add(tache)
                session.add(document)
                session.commit()
                session.refresh(tache)
                tache_id = tache.id

        if tache_id is not None:
            notifier_tache(tache_id)
        return tache_id
    except Exception as erreur:
        logger.exception(
            "Impossible de planifier la fiche pédagogique du document #%s (%s).",
            document_id,
            type(erreur).__name__,
        )
        return None


def planifier_fiche_revision_document(
    document_id: int,
    forcer: bool = False,
) -> Optional[int]:
    """Met en file une fiche téléchargeable depuis le contenu d'un cours approuvé."""
    tache_id = None
    notifier = False
    maintenant = datetime.utcnow()
    try:
        with Session(engine) as session:
            document = session.get(Document, document_id)
            if (
                not document
                or document.statut != StatutDocument.APPROUVE
                or document.type_document != TypeDocument.COURS
            ):
                return None

            fiche = session.exec(
                select(FicheRevisionDocument)
                .where(FicheRevisionDocument.document_id == document_id)
                .limit(1)
            ).first()
            if (
                fiche
                and fiche.statut == StatutFicheRevisionDocument.TERMINEE
                and fiche.contenu_json not in {"", "{}"}
            ):
                return None
            if fiche and fiche.statut == StatutFicheRevisionDocument.ECHOUEE and not forcer:
                return None
            if fiche is None:
                fiche = FicheRevisionDocument(
                    document_id=document_id,
                    statut=StatutFicheRevisionDocument.EN_ATTENTE,
                )
                session.add(fiche)
                session.flush()

            tache = session.exec(
                select(TacheIA)
                .where(
                    TacheIA.type_tache == TYPE_FICHE_REVISION_DOCUMENT,
                    TacheIA.fiche_revision_document_id == fiche.id,
                )
                .limit(1)
            ).first()

            if tache and tache.statut == StatutTacheIA.EN_COURS and not forcer:
                fiche.statut = StatutFicheRevisionDocument.EN_COURS
                fiche.date_modification = maintenant
                session.add(fiche)
                session.commit()
                return tache.id

            if tache and tache.statut == StatutTacheIA.EN_ATTENTE and not forcer:
                tache.disponible_le = min(tache.disponible_le or maintenant, maintenant)
                tache.derniere_erreur = None
                notifier = True
            elif tache:
                tache.statut = StatutTacheIA.EN_ATTENTE
                tache.nombre_essais = 0
                tache.disponible_le = maintenant
                tache.prise_en_charge_le = None
                tache.terminee_le = None
                tache.derniere_erreur = None
                notifier = True
            else:
                tache = TacheIA(
                    type_tache=TYPE_FICHE_REVISION_DOCUMENT,
                    tentative_quiz_id=None,
                    session_tuteur_id=None,
                    document_id=None,
                    fiche_revision_cours_id=None,
                    fiche_revision_document_id=fiche.id,
                    statut=StatutTacheIA.EN_ATTENTE,
                    strategie_verification="revision_depuis_document_cours",
                    score_risque=0,
                    nombre_essais=0,
                    disponible_le=maintenant,
                    date_creation=maintenant,
                )
                session.add(tache)
                notifier = True

            fiche.statut = StatutFicheRevisionDocument.EN_ATTENTE
            fiche.erreur_generation = None
            fiche.date_modification = maintenant
            session.add(fiche)
            session.add(tache)
            session.commit()
            session.refresh(tache)
            tache_id = tache.id

        if tache_id is not None and notifier:
            notifier_tache(tache_id)
        return tache_id
    except Exception as erreur:
        logger.exception(
            "Impossible de planifier la fiche de révision du document de cours #%s (%s).",
            document_id,
            type(erreur).__name__,
        )
        return None


def planifier_fiches_revision_documents_manquantes(max_documents: int = 3) -> int:
    """Rattrape progressivement les cours approuvés déposés avant cette fonction."""
    limite = max(1, min(int(max_documents or 1), 10))
    with Session(engine) as session:
        ids = session.exec(
            select(Document.id)
            .outerjoin(
                FicheRevisionDocument,
                FicheRevisionDocument.document_id == Document.id,
            )
            .where(
                Document.statut == StatutDocument.APPROUVE,
                Document.type_document == TypeDocument.COURS,
                FicheRevisionDocument.id.is_(None),
            )
            .order_by(Document.date_upload, Document.id)
            .limit(limite)
        ).all()
    total = 0
    for document_id in ids:
        if planifier_fiche_revision_document(int(document_id)) is not None:
            total += 1
    if total:
        logger.info("Fiches de révision document historiques planifiées: %s.", total)
    return total


def reparer_fiches_revision_documents_bloquees(
    max_documents: int = 5,
    document_ids: Optional[list[int]] = None,
) -> int:
    """Répare les fiches en attente/en cours dont la tâche IA manque ou est terminale.

    Les tâches encore en attente ou en cours ne sont pas renotifiées à chaque
    affichage de la bibliothèque. Les fiches ayant réellement échoué restent
    en échec et nécessitent la relance explicite réservée au déposant/admin.
    """
    limite = max(1, min(int(max_documents or 1), 10))
    with Session(engine) as session:
        requete = (
            select(
                FicheRevisionDocument.id,
                FicheRevisionDocument.document_id,
                FicheRevisionDocument.statut,
                FicheRevisionDocument.contenu_json,
            )
            .join(Document, Document.id == FicheRevisionDocument.document_id)
            .where(
                Document.statut == StatutDocument.APPROUVE,
                Document.type_document == TypeDocument.COURS,
                or_(
                    FicheRevisionDocument.statut.in_([
                        StatutFicheRevisionDocument.EN_ATTENTE,
                        StatutFicheRevisionDocument.EN_COURS,
                    ]),
                    (
                        (FicheRevisionDocument.statut == StatutFicheRevisionDocument.TERMINEE)
                        & (FicheRevisionDocument.contenu_json.in_(["", "{}"]))
                    ),
                ),
            )
            .order_by(FicheRevisionDocument.date_modification, FicheRevisionDocument.id)
            .limit(limite)
        )
        if document_ids is not None:
            ids_cibles = [int(value) for value in document_ids if value is not None]
            if not ids_cibles:
                return 0
            requete = requete.where(Document.id.in_(ids_cibles))
        fiches = session.exec(requete).all()
        if not fiches:
            return 0

        ids_fiches = [int(fiche_id) for fiche_id, _, _, _ in fiches]
        taches = session.exec(
            select(TacheIA)
            .where(
                TacheIA.type_tache == TYPE_FICHE_REVISION_DOCUMENT,
                TacheIA.fiche_revision_document_id.in_(ids_fiches),
            )
            .order_by(TacheIA.id.desc())
        ).all()

    # S'il y avait des doublons historiques, on préfère toute tâche active à
    # une ancienne tâche terminale afin de ne pas remettre un travail en double.
    taches_par_fiche: dict[int, TacheIA] = {}
    priorite = {
        StatutTacheIA.EN_COURS: 3,
        StatutTacheIA.EN_ATTENTE: 2,
        StatutTacheIA.TERMINEE: 1,
        StatutTacheIA.ECHOUEE: 0,
    }
    for tache in taches:
        fiche_id = tache.fiche_revision_document_id
        if fiche_id is None:
            continue
        precedente = taches_par_fiche.get(int(fiche_id))
        if precedente is None or priorite.get(tache.statut, -1) > priorite.get(precedente.statut, -1):
            taches_par_fiche[int(fiche_id)] = tache

    reparations = 0
    for fiche_id, document_id, fiche_statut, contenu_json in fiches:
        tache = taches_par_fiche.get(int(fiche_id))
        contenu_absent = str(contenu_json or "").strip() in {"", "{}"}
        fiche_terminee_incomplete = (
            fiche_statut == StatutFicheRevisionDocument.TERMINEE and contenu_absent
        )
        if (
            fiche_terminee_incomplete
            or tache is None
            or tache.statut in {
                StatutTacheIA.ECHOUEE,
                StatutTacheIA.TERMINEE,
            }
        ):
            if planifier_fiche_revision_document(int(document_id)) is not None:
                reparations += 1

    if reparations:
        logger.info("Fiches de révision document réparées: %s.", reparations)
    return reparations


def planifier_resumes_documents_manquants(max_documents: int = 3) -> int:
    """Met progressivement en file les documents historiques sans fiche."""
    limite = max(1, min(int(max_documents or 1), 20))
    with Session(engine) as session:
        ids = session.exec(
            select(Document.id)
            .where(or_(
                Document.resume_statut_ia == "a_generer",
                Document.resume_statut_ia_mg == "a_generer",
            ))
            .order_by(Document.date_upload, Document.id)
            .limit(limite)
        ).all()
    planifies = 0
    for document_id in ids:
        if planifier_resume_document(int(document_id)):
            planifies += 1
    if planifies:
        logger.info("Fiches pédagogiques historiques planifiées: %s.", planifies)
    return planifies


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




def _assurer_tache_fiche_revision(
    session: Session,
    fiche: FicheRevisionCours,
    forcer: bool = False,
) -> tuple[Optional[int], bool]:
    """Garantit une tâche durable sans doubler les traitements actifs."""
    if fiche.statut == StatutFicheRevisionCours.TERMINEE and fiche.contenu_json != "{}":
        return None, False
    if fiche.statut == StatutFicheRevisionCours.ECHOUEE and not forcer:
        return None, False

    maintenant = datetime.utcnow()
    tache = session.exec(
        select(TacheIA)
        .where(
            TacheIA.type_tache == TYPE_FICHE_REVISION_COURS,
            TacheIA.fiche_revision_cours_id == fiche.id,
        )
        .limit(1)
    ).first()

    if tache and tache.statut == StatutTacheIA.EN_COURS and not forcer:
        return tache.id, False

    if tache and tache.statut == StatutTacheIA.EN_ATTENTE and not forcer:
        tache.disponible_le = min(tache.disponible_le or maintenant, maintenant)
        tache.derniere_erreur = None
        session.add(tache)
        fiche.statut = StatutFicheRevisionCours.EN_ATTENTE
        fiche.erreur_generation = None
        fiche.date_modification = maintenant
        session.add(fiche)
        return tache.id, True

    if tache:
        # Une nouvelle tentative est explicite après un échec. Une tâche déjà
        # terminée mais sans fiche enregistrée est réparée automatiquement.
        tache.statut = StatutTacheIA.EN_ATTENTE
        tache.nombre_essais = 0
        tache.disponible_le = maintenant
        tache.prise_en_charge_le = None
        tache.terminee_le = None
        tache.derniere_erreur = None
    else:
        tache = TacheIA(
            type_tache=TYPE_FICHE_REVISION_COURS,
            tentative_quiz_id=None,
            session_tuteur_id=None,
            document_id=None,
            fiche_revision_cours_id=fiche.id,
            statut=StatutTacheIA.EN_ATTENTE,
            strategie_verification="fiche_revision_personnalisee",
            score_risque=0,
            nombre_essais=0,
            disponible_le=maintenant,
            date_creation=maintenant,
        )
    fiche.statut = StatutFicheRevisionCours.EN_ATTENTE
    fiche.erreur_generation = None
    fiche.date_modification = maintenant
    session.add(fiche)
    session.add(tache)
    session.flush()
    return tache.id, True


def planifier_fiche_revision_cours(
    seance_id: int,
    utilisateur_id: int,
    forcer: bool = False,
) -> Optional[int]:
    """Crée/relance la fiche d'un étudiant inscrit à une séance terminée."""
    id_tache = None
    fiche_id = None
    notifier = False
    try:
        with Session(engine) as session:
            seance = session.get(Seance, seance_id)
            if not seance or seance.statut != StatutSeance.TERMINEE:
                return None
            inscription = session.exec(
                select(InscriptionCours).where(
                    InscriptionCours.cours_id == seance.cours_id,
                    InscriptionCours.utilisateur_id == utilisateur_id,
                )
            ).first()
            if not inscription:
                return None

            fiche = session.exec(
                select(FicheRevisionCours).where(
                    FicheRevisionCours.seance_id == seance_id,
                    FicheRevisionCours.utilisateur_id == utilisateur_id,
                )
            ).first()
            creee = fiche is None
            if fiche is None:
                fiche = FicheRevisionCours(
                    cours_id=seance.cours_id,
                    seance_id=seance_id,
                    utilisateur_id=utilisateur_id,
                    statut=StatutFicheRevisionCours.EN_ATTENTE,
                )
                session.add(fiche)
                session.flush()
            fiche_id = fiche.id
            if fiche.statut == StatutFicheRevisionCours.ECHOUEE and not forcer:
                session.commit()
                return fiche_id
            id_tache, notifier = _assurer_tache_fiche_revision(session, fiche, forcer=forcer)
            session.commit()
            if creee and id_tache is not None:
                logger.info(
                    "Fiche de révision planifiée: cours=%s séance=%s étudiant=%s fiche=%s tâche=%s.",
                    seance.cours_id, seance_id, utilisateur_id, fiche_id, id_tache,
                )
        if id_tache is not None and notifier:
            notifier_tache(id_tache)
        return fiche_id
    except Exception as erreur:
        logger.exception(
            "Impossible de planifier la fiche de révision séance=%s étudiant=%s (%s).",
            seance_id, utilisateur_id, type(erreur).__name__,
        )
        return fiche_id


def planifier_fiches_revision_cours(
    cours_id: int,
    utilisateur_id: Optional[int] = None,
    seance_id: Optional[int] = None,
) -> int:
    """Planifie les fiches manquantes de toutes les séances terminées d'un cours.

    En fin de séance, tous les inscrits sont ciblés. À l'inscription tardive
    ou au retour d'un étudiant, seul son historique manquant est complété.
    """
    with Session(engine) as session:
        requete = select(Seance).where(
            Seance.cours_id == cours_id,
            Seance.statut == StatutSeance.TERMINEE,
        )
        if seance_id is not None:
            requete = requete.where(Seance.id == seance_id)
        seances = session.exec(requete.order_by(Seance.date_creation)).all()
        if not seances:
            return 0
        if utilisateur_id is not None:
            ids_etudiants = [int(utilisateur_id)]
        else:
            ids_etudiants = session.exec(
                select(InscriptionCours.utilisateur_id)
                .where(InscriptionCours.cours_id == cours_id)
            ).all()
    total = 0
    for seance in seances:
        for etudiant_id in ids_etudiants:
            if planifier_fiche_revision_cours(seance.id, int(etudiant_id)) is not None:
                total += 1
    return total


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
            if tache.type_tache == TYPE_FICHE_REVISION_COURS and tache.fiche_revision_cours_id:
                fiche_revision = session.get(FicheRevisionCours, tache.fiche_revision_cours_id)
                if fiche_revision and fiche_revision.statut == StatutFicheRevisionCours.EN_COURS:
                    fiche_revision.statut = StatutFicheRevisionCours.EN_ATTENTE
                    fiche_revision.date_modification = maintenant
                    session.add(fiche_revision)
            if tache.type_tache == TYPE_FICHE_REVISION_DOCUMENT and tache.fiche_revision_document_id:
                fiche_document = session.get(FicheRevisionDocument, tache.fiche_revision_document_id)
                if fiche_document and fiche_document.statut == StatutFicheRevisionDocument.EN_COURS:
                    fiche_document.statut = StatutFicheRevisionDocument.EN_ATTENTE
                    fiche_document.date_modification = maintenant
                    session.add(fiche_document)
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
            if tache.type_tache == TYPE_RESUME_DOCUMENT and tache.document_id:
                # Clôture l’état de la fiche si toutes les tentatives ont échoué.
                # Une fiche française déjà enregistrée reste utilisable si seule
                # la traduction malagasy n’a pas pu être obtenue.
                document = session.get(Document, tache.document_id)
                if document:
                    if document.resume_statut_ia not in {"generee", "provisoire", "insuffisante", "indisponible"}:
                        document.resume_statut_ia = "indisponible"
                    if document.resume_statut_ia_mg not in {"generee", "indisponible"}:
                        document.resume_statut_ia_mg = "indisponible"
                    session.add(document)
            if tache.type_tache == TYPE_FICHE_REVISION_COURS and tache.fiche_revision_cours_id:
                fiche_revision = session.get(FicheRevisionCours, tache.fiche_revision_cours_id)
                if fiche_revision:
                    fiche_revision.statut = StatutFicheRevisionCours.ECHOUEE
                    fiche_revision.erreur_generation = tache.derniere_erreur[:500]
                    fiche_revision.date_modification = datetime.utcnow()
                    session.add(fiche_revision)
            if tache.type_tache == TYPE_FICHE_REVISION_DOCUMENT and tache.fiche_revision_document_id:
                fiche_document = session.get(FicheRevisionDocument, tache.fiche_revision_document_id)
                if fiche_document:
                    fiche_document.statut = StatutFicheRevisionDocument.ECHOUEE
                    fiche_document.erreur_generation = tache.derniere_erreur[:500]
                    fiche_document.date_modification = datetime.utcnow()
                    session.add(fiche_document)
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
            if tache.type_tache == TYPE_FICHE_REVISION_COURS and tache.fiche_revision_cours_id:
                fiche_revision = session.get(FicheRevisionCours, tache.fiche_revision_cours_id)
                if fiche_revision:
                    fiche_revision.statut = StatutFicheRevisionCours.EN_ATTENTE
                    fiche_revision.erreur_generation = None
                    fiche_revision.date_modification = datetime.utcnow()
                    session.add(fiche_revision)
            if tache.type_tache == TYPE_FICHE_REVISION_DOCUMENT and tache.fiche_revision_document_id:
                fiche_document = session.get(FicheRevisionDocument, tache.fiche_revision_document_id)
                if fiche_document:
                    fiche_document.statut = StatutFicheRevisionDocument.EN_ATTENTE
                    fiche_document.erreur_generation = None
                    fiche_document.date_modification = datetime.utcnow()
                    session.add(fiche_document)
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
