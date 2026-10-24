"""Bilan de reprise deterministic et personnalise pour l'apprenant.

Toutes les informations viennent des enregistrements de l'utilisateur courant.
Ce module ne fait aucun appel IA et ne modifie aucun historique pendant la lecture.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlmodel import Session, select
from sqlalchemy import func

from .models import (
    ActionGamification,
    ConsultationDocument,
    Document,
    JeuCerebralSession,
    MissionApprentissage,
    ProgressionNotion,
    RoleUtilisateur,
    SessionTuteur,
    StatutDocument,
    TentativeQuiz,
)
from . import adaptive_learning, knowledge_map, learning_session, quiz as quiz_module, subscription


MAX_PERIODE_JOURS = 30
NB_ACTIVITES_AFFICHER = 8
NB_NOTIONS_AFFICHER = 6


def _utc_naif(moment: datetime) -> datetime:
    if moment.tzinfo is not None:
        return moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def _iso_utc(moment: Optional[datetime]) -> Optional[str]:
    if moment is None:
        return None
    return _utc_naif(moment).replace(tzinfo=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normaliser_date_depuis(valeur: Any, maintenant: Optional[datetime] = None) -> datetime:
    """Lit un epoch millisecondes (client), accepte aussi les secondes/ISO.

    Une valeur locale ne sert qu'à borner la période d'affichage; elle ne sert
    jamais à identifier un utilisateur ni à autoriser l'accès à ses données.
    """
    maintenant = _utc_naif(maintenant or datetime.utcnow())
    minimum = maintenant - timedelta(days=MAX_PERIODE_JOURS)
    moment: Optional[datetime] = None

    if valeur is not None:
        try:
            nombre = float(valeur)
            if nombre > 100_000_000_000:
                moment = datetime.fromtimestamp(nombre / 1000, tz=timezone.utc).replace(tzinfo=None)
            elif nombre > 1_000_000_000:
                moment = datetime.fromtimestamp(nombre, tz=timezone.utc).replace(tzinfo=None)
        except (TypeError, ValueError, OverflowError, OSError):
            moment = None

        if moment is None:
            try:
                texte = str(valeur).strip()
                if texte:
                    moment = datetime.fromisoformat(texte.replace("Z", "+00:00"))
                    moment = _utc_naif(moment)
            except (TypeError, ValueError, OverflowError):
                moment = None

    if moment is None:
        moment = maintenant - timedelta(days=1)
    if moment > maintenant:
        moment = maintenant
    if moment < minimum:
        moment = minimum
    return moment


def _compter(
    session: Session,
    modele: Any,
    utilisateur_id: int,
    colonne_date: Any,
    depuis: datetime,
    *conditions: Any,
) -> int:
    requete = (
        select(func.count())
        .select_from(modele)
        .where(modele.utilisateur_id == utilisateur_id)
        .where(colonne_date >= depuis)
    )
    for condition in conditions:
        requete = requete.where(condition)
    return int(session.exec(requete).one() or 0)


def _moment_evenement(evenement: dict) -> datetime:
    return evenement.pop("_moment")


def _statut_progression(progression: ProgressionNotion) -> dict:
    score = max(0, min(100, int(progression.score_maitrise or 0)))
    maitrise = False
    try:
        diagnostic = quiz_module.diagnostiquer_maitrise(progression)
        score = max(0, min(100, int(diagnostic.get("score", score) or 0)))
        maitrise = bool(diagnostic.get("maitrise_confirmee"))
    except (AttributeError, KeyError, TypeError, ValueError):
        maitrise = bool(getattr(progression, "maitrise_confirmee", False))

    if maitrise:
        etat = "maitrise_confirmee"
        libelle = "Maîtrise confirmée"
    elif score >= 75:
        etat = "solide_a_confirmer"
        libelle = "Bon résultat, à confirmer"
    elif score >= 50:
        etat = "en_consolidation"
        libelle = "En consolidation"
    else:
        etat = "a_renforcer"
        libelle = "À renforcer"
    return {"score": score, "maitrise_confirmee": maitrise, "etat": etat, "libelle": libelle}


def _acces_ia(session: Session, utilisateur: Any) -> bool:
    role = getattr(getattr(utilisateur, "role", None), "value", getattr(utilisateur, "role", None))
    if role == RoleUtilisateur.ADMIN.value:
        return True
    try:
        abonnement = subscription.obtenir_abonnement(session, int(utilisateur.id))
        return subscription.acces_ia_valide(abonnement)
    except Exception:
        # Un problème de lecture d'abonnement ne doit pas exposer des liens
        # présentés comme utilisables; la route d'accès appliquera son propre contrôle.
        return False


def _mission_pour_reprise(
    session: Session,
    utilisateur_id: int,
    progressions: list[ProgressionNotion],
) -> dict:
    """Lit la mission persistante ou propose la prochaine mission sans l'écrire."""
    progres_par_id = {int(p.id): p for p in progressions if p.id is not None}
    etat = session.exec(
        select(MissionApprentissage).where(MissionApprentissage.utilisateur_id == utilisateur_id)
    ).first()

    if etat and etat.statut == "active":
        progression = progres_par_id.get(int(etat.progression_id))
        if progression is None:
            candidate = session.get(ProgressionNotion, etat.progression_id)
            if candidate and candidate.utilisateur_id == utilisateur_id:
                progression = candidate
                progres_par_id[int(candidate.id)] = candidate
                progressions.append(candidate)
        if progression is not None:
            base = learning_session.construire_mission(
                {"prochaine": {
                    "id": progression.id,
                    "matiere": progression.matiere,
                    "notion": progression.notion,
                    "score": progression.score_maitrise,
                }},
                progressions,
            )
            return adaptive_learning.appliquer_etat(base, etat)

    carte = knowledge_map.construire_carte(progressions)
    exclure_id = etat.progression_id if etat and etat.statut == "terminee" else None
    cible = adaptive_learning.choisir_prochaine_notion(carte, progressions, exclure_id=exclure_id)
    if cible:
        return learning_session.construire_mission({"prochaine": cible}, progressions)

    if progressions and all(_statut_progression(p)["maitrise_confirmee"] for p in progressions):
        return adaptive_learning.vue_toutes_notions_confirmees()
    return learning_session.construire_mission({"prochaine": None}, progressions)


def _resumer_mission(mission: dict, acces_ia: bool) -> dict:
    active = bool(mission.get("active")) and mission.get("etat_mission") != "terminee"
    toutes_confirmees = bool(mission.get("toutes_confirmees"))
    if active:
        action = mission.get("action_principale")
        methode = (
            "Comprendre avec le Tuteur IA, puis s'entraîner sur la même notion."
            if action == "tuteur"
            else "Pratiquer avec un quiz ciblé, puis vérifier si la maîtrise tient."
        )
        return {
            "type": "active",
            "active": True,
            "etape": str(mission.get("etape_courante") or ("comprendre" if action == "tuteur" else "pratiquer")),
            "action": str(action or "quiz"),
            "titre": str(mission.get("titre") or "Poursuivre ta mission"),
            "matiere": str(mission.get("matiere") or ""),
            "notion": str(mission.get("notion") or ""),
            "score": mission.get("score"),
            "objectif": str(mission.get("objectif") or ""),
            "methode": methode,
            "lien": "/session-apprentissage" if acces_ia else "/abonnement?ia_requis=1",
            "libelle_action": (
                str(mission.get("action_label") or "Reprendre ma mission")
                if acces_ia else "Voir les options d'accès"
            ),
        }
    if toutes_confirmees:
        return {
            "type": "toutes_confirmees",
            "active": False,
            "etape": "terminee",
            "action": "quiz",
            "titre": str(mission.get("titre") or "Prêt pour une nouvelle notion"),
            "matiere": "",
            "notion": "",
            "score": None,
            "objectif": str(mission.get("objectif") or "Explore une nouvelle notion pour enrichir ta carte."),
            "methode": "Choisis un thème nouveau dans un quiz pour créer une nouvelle preuve.",
            "lien": "/quiz" if acces_ia else "/abonnement?ia_requis=1",
            "libelle_action": "Explorer une nouvelle notion" if acces_ia else "Voir les options d'accès",
        }
    return {
        "type": "nouvelle",
        "active": False,
        "etape": "comprendre",
        "action": "quiz",
        "titre": "Préparer ta prochaine mission",
        "matiere": "",
        "notion": "",
        "score": None,
        "objectif": "Un premier quiz permet d'identifier les notions à travailler et de préparer une mission guidée.",
        "methode": "Commence par un quiz; le parcours s'adaptera ensuite à tes réponses.",
        "lien": "/quiz" if acces_ia else "/abonnement?ia_requis=1",
        "libelle_action": "Lancer un quiz" if acces_ia else "Voir les options d'accès",
    }


def construire_bilan(
    session: Session,
    utilisateur: Any,
    depuis: Any = None,
    maintenant: Optional[datetime] = None,
) -> dict:
    """Produit un résumé factuel; tous les accès SQL sont filtrés par utilisateur_id."""
    maintenant = _utc_naif(maintenant or datetime.utcnow())
    utilisateur_id = int(utilisateur.id)
    moment_depart = normaliser_date_depuis(depuis, maintenant)
    acces_ia = _acces_ia(session, utilisateur)

    quiz = session.exec(
        select(TentativeQuiz)
        .where(
            TentativeQuiz.utilisateur_id == utilisateur_id,
            TentativeQuiz.date_soumission != None,  # noqa: E711
            TentativeQuiz.date_soumission >= moment_depart,
        )
        .order_by(TentativeQuiz.date_soumission.desc())
        .limit(NB_ACTIVITES_AFFICHER)
    ).all()
    nb_quiz = _compter(
        session, TentativeQuiz, utilisateur_id, TentativeQuiz.date_soumission,
        moment_depart, TentativeQuiz.date_soumission != None,  # noqa: E711
    )

    consultations = session.exec(
        select(ConsultationDocument, Document)
        .join(Document, Document.id == ConsultationDocument.document_id)
        .where(
            ConsultationDocument.utilisateur_id == utilisateur_id,
            ConsultationDocument.date_consultation >= moment_depart,
            Document.statut == StatutDocument.APPROUVE,
        )
        .order_by(ConsultationDocument.date_consultation.desc())
        .limit(NB_ACTIVITES_AFFICHER)
    ).all()
    nb_documents = int(session.exec(
        select(func.count())
        .select_from(ConsultationDocument)
        .join(Document, Document.id == ConsultationDocument.document_id)
        .where(
            ConsultationDocument.utilisateur_id == utilisateur_id,
            ConsultationDocument.date_consultation >= moment_depart,
            Document.statut == StatutDocument.APPROUVE,
        )
    ).one() or 0)

    seances_tuteur = session.exec(
        select(SessionTuteur)
        .where(
            SessionTuteur.utilisateur_id == utilisateur_id,
            SessionTuteur.date_creation >= moment_depart,
        )
        .order_by(SessionTuteur.date_creation.desc())
        .limit(NB_ACTIVITES_AFFICHER)
    ).all()
    nb_tuteur = _compter(
        session, SessionTuteur, utilisateur_id, SessionTuteur.date_creation, moment_depart
    )

    jeux = session.exec(
        select(JeuCerebralSession)
        .where(
            JeuCerebralSession.utilisateur_id == utilisateur_id,
            JeuCerebralSession.date_fin != None,  # noqa: E711
            JeuCerebralSession.date_fin >= moment_depart,
        )
        .order_by(JeuCerebralSession.date_fin.desc())
        .limit(NB_ACTIVITES_AFFICHER)
    ).all()
    nb_jeux = _compter(
        session, JeuCerebralSession, utilisateur_id, JeuCerebralSession.date_fin,
        moment_depart, JeuCerebralSession.date_fin != None,  # noqa: E711
    )

    activites: list[dict] = []
    for tentative in quiz:
        pourcentage = round(100 * tentative.score / tentative.nb_questions) if tentative.score is not None and tentative.nb_questions else 0
        activites.append({
            "type": "quiz",
            "matiere": str(tentative.matiere or "Matière non précisée")[:120],
            "score": tentative.score,
            "nb_questions": int(tentative.nb_questions or 0),
            "pourcentage": pourcentage,
            "_moment": tentative.date_soumission or tentative.date_creation,
        })
    for consultation, document in consultations:
        activites.append({
            "type": "document",
            "titre": str(document.titre or "Document consulté")[:150],
            "matiere": str(document.matiere or "Matière non précisée")[:120],
            "_moment": consultation.date_consultation,
        })
    for seance in seances_tuteur:
        notion = (seance.notion or "").strip()
        question = " ".join(str(seance.question or "").split())
        detail = question[:140] + ("…" if len(question) > 140 else "")
        activites.append({
            "type": "tuteur",
            "notion": notion[:120],
            "question": detail or "",
            "_moment": seance.date_creation,
        })
    for jeu in jeux:
        theme = str(jeu.theme_id or "Défi").replace("_", " ").strip().capitalize()
        activites.append({
            "type": "jeu",
            "theme": theme[:80],
            "score": jeu.score,
            "bonnes_reponses": jeu.bonnes_reponses,
            "nb_questions": jeu.nb_questions,
            "_moment": jeu.date_fin or jeu.date_creation,
        })
    activites.sort(key=lambda item: item["_moment"], reverse=True)
    activites = activites[:NB_ACTIVITES_AFFICHER]
    for activite in activites:
        activite["date"] = _iso_utc(_moment_evenement(activite))

    progressions_recentes = session.exec(
        select(ProgressionNotion)
        .where(
            ProgressionNotion.utilisateur_id == utilisateur_id,
            ProgressionNotion.nb_questions > 0,
            ProgressionNotion.date_maj >= moment_depart,
        )
        .order_by(ProgressionNotion.date_maj.desc())
        .limit(NB_NOTIONS_AFFICHER)
    ).all()
    apprentissages = []
    for progression in progressions_recentes:
        diagnostic = _statut_progression(progression)
        apprentissages.append({
            "matiere": str(progression.matiere or "Matière non précisée")[:120],
            "notion": str(progression.notion or "Notion travaillée")[:160],
            "score": diagnostic["score"],
            "etat": diagnostic["etat"],
            "libelle": diagnostic["libelle"],
            "questions": max(0, int(progression.nb_questions or 0)),
            "date": _iso_utc(progression.date_maj),
        })

    progressions = session.exec(
        select(ProgressionNotion)
        .where(ProgressionNotion.utilisateur_id == utilisateur_id)
        .where(ProgressionNotion.nb_questions > 0)
        .order_by(ProgressionNotion.score_maitrise.asc(), ProgressionNotion.date_maj.desc())
        .limit(250)
    ).all()

    renforcer = []
    for progression in progressions:
        diagnostic = _statut_progression(progression)
        due = bool(progression.prochaine_revision_le and _utc_naif(progression.prochaine_revision_le) <= maintenant)
        erreurs = max(0, int(progression.nb_erreurs or 0))
        score = diagnostic["score"]
        if not (score < 70 or erreurs >= 2 or due):
            continue
        if due:
            raison_code = "revision_due"
            raison = "Révision prévue : c'est le bon moment pour réactiver cette notion."
        elif score < 50:
            raison_code = "score_low"
            raison = f"Score de maîtrise à {score} % : reprends la méthode avec un exemple guidé."
        elif erreurs >= 2:
            raison_code = "repeated_errors"
            raison = f"{erreurs} erreurs enregistrées : identifie l'étape qui bloque avant de refaire un quiz."
        else:
            raison_code = "score_stabilize"
            raison = f"Score de maîtrise à {score} % : quelques questions ciblées aideront à stabiliser l'acquis."
        renforcer.append({
            "matiere": str(progression.matiere or "Matière non précisée")[:120],
            "notion": str(progression.notion or "Notion à revoir")[:160],
            "score": score,
            "erreurs": erreurs,
            "raison_code": raison_code,
            "raison": raison,
            "date": _iso_utc(progression.date_maj),
            "_priority": (0 if due else 1, score, -erreurs, _utc_naif(progression.date_maj)),
        })
    renforcer.sort(key=lambda item: item["_priority"])
    renforcer = renforcer[:4]
    for item in renforcer:
        item.pop("_priority", None)

    mission_interne = _mission_pour_reprise(session, utilisateur_id, progressions)
    mission = _resumer_mission(mission_interne, acces_ia)

    if not acces_ia:
        methodes = [
            {
                "titre": "Fiches de révision",
                "description": "Reprends les notions et exemples de tes cours approuvés.",
                "lien": "/mes-revisions",
            },
            {
                "titre": "Carte de connaissances",
                "description": "Visualise les notions déjà évaluées et leurs points fragiles.",
                "lien": "/carte-connaissances",
            },
            {
                "titre": "Accès aux outils IA",
                "description": "Consulte les options pour retrouver le Quiz ciblé et le Tuteur IA.",
                "lien": "/abonnement?ia_requis=1",
            },
        ]
    else:
        methodes = [
            {
                "titre": "Tuteur IA",
                "description": "Demande une explication progressive et un exemple sur ton erreur.",
                "lien": "/tuteur",
            },
            {
                "titre": "Quiz ciblé",
                "description": "Teste la même notion avec de nouvelles questions, sans te limiter à relire.",
                "lien": "/quiz",
            },
            {
                "titre": "Fiches de révision",
                "description": "Revois les notions, formules et exemples tirés des cours disponibles.",
                "lien": "/mes-revisions",
            },
            {
                "titre": "Carte de connaissances",
                "description": "Repère les notions à consolider et les prérequis déjà maîtrisés.",
                "lien": "/carte-connaissances",
            },
        ]

    return {
        "genere_le": _iso_utc(maintenant),
        "depuis": _iso_utc(moment_depart),
        "stats": {
            "quiz": nb_quiz,
            "documents": nb_documents,
            "tuteur": nb_tuteur,
            "jeux": nb_jeux,
        },
        "activites": activites,
        "apprentissages": apprentissages,
        "renforcer": renforcer,
        "mission": mission,
        "methodes": methodes,
        "acces_ia": acces_ia,
        "has_activity": bool(nb_quiz or nb_documents or nb_tuteur or nb_jeux),
        "has_learning_data": bool(progressions),
    }
