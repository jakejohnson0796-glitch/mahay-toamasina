import random
from typing import List, Optional

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from ..database import get_session
from ..auth import utilisateur_courant
from ..dependencies import acces_premium_ou_redirection
from ..models import Document, StatutDocument, TentativeQuiz
from .. import quiz as quiz_module
from .. import ai_quiz

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _matieres_disponibles(session: Session) -> List[str]:
    valeurs = session.exec(
        select(Document.matiere).where(Document.statut == StatutDocument.APPROUVE).distinct()
    ).all()
    return sorted(valeurs)


@router.get("/quiz")
def page_config_quiz(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    return templates.TemplateResponse(
        request,
        "quiz_config.html",
        {
            "utilisateur": utilisateur,
            "matieres": _matieres_disponibles(session),
            "niveaux": quiz_module.NIVEAUX,
            "difficultes": quiz_module.DIFFICULTES,
            "nb_questions_possibles": quiz_module.NB_QUESTIONS_POSSIBLES,
        },
    )


@router.post("/quiz/generer")
def generer_quiz(
    request: Request,
    matiere: Optional[str] = Form(None),
    matiere_libre: Optional[str] = Form(None),
    niveau: str = Form(...),
    difficulte: str = Form(...),
    nb_questions: int = Form(10),
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    matiere_choisie = (matiere_libre or "").strip() or (matiere or "").strip()
    if not matiere_choisie:
        return RedirectResponse("/quiz?erreur=matiere_requise", status_code=303)

    nb_questions = nb_questions if nb_questions in quiz_module.NB_QUESTIONS_POSSIBLES else 10

    tentative = quiz_module.creer_tentative(session, utilisateur, matiere_choisie, niveau, difficulte, nb_questions)
    return RedirectResponse(f"/quiz/{tentative.id}", status_code=303)


@router.get("/quiz/historique")
def page_historique(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    tentatives = quiz_module.historique(session, utilisateur.id)
    stats = quiz_module.statistiques(tentatives)

    return templates.TemplateResponse(
        request,
        "quiz_historique.html",
        {"utilisateur": utilisateur, "tentatives": tentatives, "stats": stats},
    )


@router.get("/quiz/reflexion")
def page_reflexion(request: Request, matiere: Optional[str] = None, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    theme = ai_quiz.generer_theme_reflexion(matiere or None)

    return templates.TemplateResponse(
        request,
        "quiz_reflexion.html",
        {
            "utilisateur": utilisateur,
            "theme": theme,
            "matieres": _matieres_disponibles(session),
            "matiere_selectionnee": matiere or "",
        },
    )


def _tentative_du_proprietaire(session: Session, tentative_id: int, utilisateur_id: int) -> Optional[TentativeQuiz]:
    tentative = session.get(TentativeQuiz, tentative_id)
    if not tentative or tentative.utilisateur_id != utilisateur_id:
        return None
    return tentative


@router.get("/quiz/{tentative_id}")
def page_passer_quiz(request: Request, tentative_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    tentative = _tentative_du_proprietaire(session, tentative_id, utilisateur.id)
    if not tentative:
        return RedirectResponse("/quiz", status_code=303)

    if tentative.date_soumission is not None:
        return RedirectResponse(f"/quiz/{tentative.id}/resultat", status_code=303)

    return templates.TemplateResponse(
        request,
        "quiz_passer.html",
        {
            "utilisateur": utilisateur,
            "tentative": tentative,
            "questions": quiz_module.questions(tentative),
            "secondes_restantes": quiz_module.secondes_restantes_examen(tentative),
        },
    )


@router.post("/quiz/examen/generer")
def generer_examen(request: Request, session: Session = Depends(get_session)):
    """Mode examen : matiere/niveau/difficulte tires au sort par le
    serveur (pas de formulaire a remplir), nombre de questions et duree
    fixes. Meme pipeline de generation/verification que le quiz normal."""
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    matieres = _matieres_disponibles(session)
    matiere = random.choice(matieres) if matieres else "Culture generale"
    niveau = random.choice(quiz_module.NIVEAUX)
    difficulte = random.choice(quiz_module.DIFFICULTES)

    tentative = quiz_module.creer_tentative_examen(session, utilisateur, matiere, niveau, difficulte)
    return RedirectResponse(f"/quiz/{tentative.id}", status_code=303)


@router.post("/quiz/{tentative_id}/soumettre")
async def soumettre_quiz(request: Request, tentative_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    tentative = _tentative_du_proprietaire(session, tentative_id, utilisateur.id)
    if not tentative:
        return RedirectResponse("/quiz", status_code=303)

    if tentative.date_soumission is not None:
        return RedirectResponse(f"/quiz/{tentative.id}/resultat", status_code=303)

    formulaire = await request.form()
    nb = len(quiz_module.questions(tentative))
    reponses_soumises: List[Optional[int]] = []
    for i in range(nb):
        valeur = formulaire.get(f"question_{i}")
        reponses_soumises.append(int(valeur) if valeur is not None and valeur != "" else None)

    quiz_module.corriger(session, tentative, reponses_soumises)
    return RedirectResponse(f"/quiz/{tentative.id}/resultat", status_code=303)


@router.get("/quiz/{tentative_id}/resultat")
def page_resultat_quiz(request: Request, tentative_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    tentative = _tentative_du_proprietaire(session, tentative_id, utilisateur.id)
    if not tentative or tentative.date_soumission is None:
        return RedirectResponse("/quiz", status_code=303)

    return templates.TemplateResponse(
        request,
        "quiz_resultat.html",
        {
            "utilisateur": utilisateur,
            "tentative": tentative,
            "questions": quiz_module.questions(tentative),
            "reponses": quiz_module.reponses(tentative),
        },
    )


@router.post("/quiz/{tentative_id}/questions/{index_question}/signaler")
def signaler_question_quiz(
    request: Request,
    tentative_id: int,
    index_question: int,
    motif: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    tentative = _tentative_du_proprietaire(session, tentative_id, utilisateur.id)
    if not tentative or tentative.date_soumission is None:
        return RedirectResponse("/quiz", status_code=303)

    quiz_module.signaler_question(session, tentative_id, index_question, utilisateur.id, motif)

    return RedirectResponse(f"/quiz/{tentative_id}/resultat?signale=1", status_code=303)
