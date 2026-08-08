from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..auth import utilisateur_courant
from ..dependencies import acces_premium_ou_redirection
from ..models import SessionTuteur
from .. import ai_quiz

router = APIRouter()

NB_HISTORIQUE_AFFICHE = 10


@router.get("/tuteur")
def page_tuteur(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    historique = session.exec(
        select(SessionTuteur)
        .where(SessionTuteur.utilisateur_id == utilisateur.id)
        .order_by(SessionTuteur.date_creation.desc())
        .limit(NB_HISTORIQUE_AFFICHE)
    ).all()

    return templates.TemplateResponse(
        request,
        "tuteur.html",
        {"utilisateur": utilisateur, "historique": historique},
    )


@router.post("/tuteur/demander")
def demander_tuteur(request: Request, question: str = Form(...), session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    question = question.strip()
    if not question:
        return RedirectResponse("/tuteur?erreur=question_requise", status_code=303)

    reponse = ai_quiz.generer_reponse_tuteur(question)

    session_tuteur = SessionTuteur(
        utilisateur_id=utilisateur.id,
        question=question,
        explication=reponse["explication"],
        exemple=reponse["exemple"],
        exercice=reponse["exercice"],
        correction=reponse["correction"],
    )
    session.add(session_tuteur)
    session.commit()
    session.refresh(session_tuteur)

    return RedirectResponse(f"/tuteur/{session_tuteur.id}", status_code=303)


@router.get("/tuteur/{session_id}")
def page_reponse_tuteur(request: Request, session_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    session_tuteur = session.get(SessionTuteur, session_id)
    if not session_tuteur or session_tuteur.utilisateur_id != utilisateur.id:
        return RedirectResponse("/tuteur", status_code=303)

    return templates.TemplateResponse(
        request,
        "tuteur_reponse.html",
        {"utilisateur": utilisateur, "session_tuteur": session_tuteur},
    )
