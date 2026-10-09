"""Espace personnel « Mes révisions »."""
from datetime import datetime
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select, func

from ..auth import utilisateur_courant
from ..database import get_session
from ..models import ConsultationDocument, Document, ProgressionNotion, SessionTuteur, TentativeQuiz, StatutDocument
from ..templating import templates
from .. import dashboard as dashboard_module
from .. import quiz as quiz_module
from .. import gamification
from .. import knowledge_map
from .. import learning_session

router = APIRouter()


@router.get("/mes-revisions")
def page_mes_revisions(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    gamification.enregistrer_action(
        session,
        utilisateur.id,
        "revision",
        source_type="visite_revisions",
        source_key=datetime.utcnow().date().isoformat(),
    )
    session.commit()

    consultations = session.exec(
        select(ConsultationDocument, Document)
        .join(Document, ConsultationDocument.document_id == Document.id)
        .where(ConsultationDocument.utilisateur_id == utilisateur.id)
        .where(Document.statut == StatutDocument.APPROUVE)
        .order_by(ConsultationDocument.date_consultation.desc())
        .limit(20)
    ).all()

    quiz = session.exec(
        select(TentativeQuiz)
        .where(TentativeQuiz.utilisateur_id == utilisateur.id)
        .where(TentativeQuiz.date_soumission != None)  # noqa: E711
        .order_by(TentativeQuiz.date_soumission.desc())
        .limit(20)
    ).all()

    nb_sessions_tuteur = int(session.exec(
        select(func.count())
        .select_from(SessionTuteur)
        .where(SessionTuteur.utilisateur_id == utilisateur.id)
    ).one() or 0)

    progression = dashboard_module.progression_matieres(session, utilisateur)
    notions_a_revoir = quiz_module.notions_a_revoir(session, utilisateur.id, limit=8)

    progressions_maitrise = session.exec(
        select(ProgressionNotion)
        .where(ProgressionNotion.utilisateur_id == utilisateur.id)
        .where(ProgressionNotion.nb_questions > 0)
        .order_by(ProgressionNotion.score_maitrise.desc(), ProgressionNotion.date_maj.desc())
        .limit(12)
    ).all()
    cartes_maitrise = [
        {
            "progression": progression,
            "diagnostic": quiz_module.diagnostiquer_maitrise(progression),
        }
        for progression in progressions_maitrise
    ]
    carte_connaissances = knowledge_map.construire_carte(
        session.exec(
            select(ProgressionNotion)
            .where(ProgressionNotion.utilisateur_id == utilisateur.id)
            .where(ProgressionNotion.nb_questions > 0)
        ).all()
    )

    return templates.TemplateResponse(
        request,
        "mes_revisions.html",
        {
            "utilisateur": utilisateur,
            "consultations": consultations,
            "quiz": quiz,
            "nb_sessions_tuteur": nb_sessions_tuteur,
            "progression_matieres": progression,
            "notions_a_revoir": notions_a_revoir,
            "cartes_maitrise": cartes_maitrise,
            "carte_connaissances": carte_connaissances,
            "nb_documents": len(consultations),
            "nb_quiz": len(quiz),
        },
    )


@router.get("/session-apprentissage")
def page_session_apprentissage(request: Request, session: Session = Depends(get_session)):
    """Lance une mission courte centrée sur la prochaine meilleure notion."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    progressions = session.exec(
        select(ProgressionNotion)
        .where(ProgressionNotion.utilisateur_id == utilisateur.id)
        .where(ProgressionNotion.nb_questions > 0)
        .order_by(ProgressionNotion.score_maitrise.asc(), ProgressionNotion.date_maj.desc())
    ).all()
    carte = knowledge_map.construire_carte(progressions)
    mission = learning_session.construire_mission(carte, progressions)

    return templates.TemplateResponse(
        request,
        "session_apprentissage.html",
        {"utilisateur": utilisateur, "mission": mission},
    )


@router.get("/carte-connaissances")
def page_carte_connaissances(request: Request, session: Session = Depends(get_session)):
    """Affiche la carte des prerequis a partir des notions deja evaluees."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    progressions = session.exec(
        select(ProgressionNotion)
        .where(ProgressionNotion.utilisateur_id == utilisateur.id)
        .where(ProgressionNotion.nb_questions > 0)
        .order_by(ProgressionNotion.score_maitrise.asc(), ProgressionNotion.date_maj.desc())
    ).all()
    carte = knowledge_map.construire_carte(progressions)
    return templates.TemplateResponse(
        request,
        "carte_connaissances.html",
        {"utilisateur": utilisateur, "carte": carte},
    )
