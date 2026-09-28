"""Espace personnel « Mes révisions »."""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..auth import utilisateur_courant
from ..database import get_session
from ..models import ConsultationDocument, Document, SessionTuteur, TentativeQuiz, StatutDocument
from ..templating import templates
from .. import dashboard as dashboard_module

router = APIRouter()


@router.get("/mes-revisions")
def page_mes_revisions(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

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

    sessions_tuteur = session.exec(
        select(SessionTuteur)
        .where(SessionTuteur.utilisateur_id == utilisateur.id)
        .order_by(SessionTuteur.date_creation.desc())
        .limit(10)
    ).all()

    progression = dashboard_module.progression_matieres(session, utilisateur)

    return templates.TemplateResponse(
        request,
        "mes_revisions.html",
        {
            "utilisateur": utilisateur,
            "consultations": consultations,
            "quiz": quiz,
            "sessions_tuteur": sessions_tuteur,
            "progression_matieres": progression,
            "nb_documents": len(consultations),
            "nb_quiz": len(quiz),
            "nb_sessions_tuteur": len(sessions_tuteur),
        },
    )
