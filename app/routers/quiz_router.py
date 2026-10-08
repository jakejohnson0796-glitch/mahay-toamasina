import logging
import random
from typing import List, Optional

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..auth import utilisateur_courant
from ..dependencies import acces_ia_ou_redirection
from ..models import Document, StatutDocument, TentativeQuiz, ProgressionNotion
from .. import quiz as quiz_module
from .. import ai_queue
from .. import theme_service
from .. import gamification
from .. import quiz_calibration
from ..rate_limit import limite_depassee

router = APIRouter()
logger = logging.getLogger(__name__)


def _matieres_disponibles(session: Session) -> List[str]:
    valeurs = session.exec(
        select(Document.matiere).where(Document.statut == StatutDocument.APPROUVE).distinct()
    ).all()
    return sorted(valeurs)


@router.get("/quiz")
def page_config_quiz(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
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
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    host = request.client.host if request.client else "inconnu"
    if limite_depassee(f"ia-quiz:user:{utilisateur.id}", 3, 300) or limite_depassee(f"ia-quiz:ip:{host}", 12, 300):
        return RedirectResponse("/quiz?erreur=trop_de_generations", status_code=303)

    matiere_choisie = (matiere_libre or "").strip() or (matiere or "").strip()
    if not matiere_choisie:
        return RedirectResponse("/quiz?erreur=matiere_requise", status_code=303)

    nb_questions = nb_questions if nb_questions in quiz_module.NB_QUESTIONS_POSSIBLES else 10
    try:
        matiere_choisie = quiz_module.valider_parametres(matiere_choisie, niveau, difficulte, nb_questions)
    except quiz_module.QuizValidationError:
        return RedirectResponse("/quiz?erreur=parametres_invalides", status_code=303)

    try:
        tentative = quiz_module.creer_tentative(
            session,
            utilisateur,
            matiere_choisie,
            niveau,
            difficulte,
            nb_questions,
        )
    except quiz_module.QuizValidationError as erreur:
        logger.warning(
            "Generation quiz invalide: user=%s matiere=%s niveau=%s difficulte=%s "
            "nb_questions=%s erreur=%s",
            utilisateur.id,
            matiere_choisie,
            niveau,
            difficulte,
            nb_questions,
            erreur,
        )
        return RedirectResponse("/quiz?erreur=generation_invalide", status_code=303)

    # La verification multi-modeles est durablement mise en file.
    # Sur Render Free, le worker tourne dans le Web et consomme Redis.
    tache_ia_id = ai_queue.planifier_verification_quiz(tentative.id)
    print(
        f"[AI QUEUE] Route /quiz/generer quiz={tentative.id} tache_ia={tache_ia_id}.",
        flush=True,
    )
    return RedirectResponse(f"/quiz/{tentative.id}", status_code=303)


@router.get("/quiz/historique")
def page_historique(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
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
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    theme = theme_service.get_theme_du_jour(matiere=matiere or None)

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
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    tentative = _tentative_du_proprietaire(session, tentative_id, utilisateur.id)
    if not tentative:
        return RedirectResponse("/quiz", status_code=303)

    questions = quiz_module.questions(tentative)
    correction_visible = tentative.date_soumission is not None

    return templates.TemplateResponse(
        request,
        "quiz_passer.html",
        {
            "utilisateur": utilisateur,
            "tentative": tentative,
            "questions": questions,
            "reponses": quiz_module.reponses(tentative) or [],
            "correction_visible": correction_visible,
            "adaptatif": quiz_module.est_quiz_adaptatif(tentative),
            "adaptatif_etat": quiz_module.etat_adaptatif(tentative) if quiz_module.est_quiz_adaptatif(tentative) else None,
            "secondes_restantes": quiz_module.secondes_restantes_examen(tentative),
        },
    )


@router.post("/quiz/{tentative_id}/repondre")
async def repondre_question_adaptative(
    request: Request,
    tentative_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Enregistre une réponse adaptative et choisit la question suivante."""
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return JSONResponse({"erreur": "acces_refuse"}, status_code=401)

    tentative = _tentative_du_proprietaire(session, tentative_id, utilisateur.id)
    if not tentative or not quiz_module.est_quiz_adaptatif(tentative):
        return JSONResponse({"erreur": "quiz_adaptatif_introuvable"}, status_code=404)

    formulaire = await request.form()
    try:
        index_question = int(str(formulaire.get("question_index")))
        reponse = int(str(formulaire.get("reponse")))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Réponse adaptative invalide.") from exc

    try:
        resultat = quiz_module.enregistrer_reponse_adaptative(
            session,
            tentative,
            index_question,
            reponse,
        )
    except quiz_module.QuizValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse(resultat)


@router.post("/quiz/cible")
def generer_quiz_cible(
    request: Request,
    progression_id: int = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Genere un mini-quiz a partir d'une faiblesse deja identifiee."""
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    progression = session.get(ProgressionNotion, progression_id)
    if not progression or progression.utilisateur_id != utilisateur.id:
        return RedirectResponse("/mes-revisions", status_code=303)
    # Une notion sans erreur peut aussi être réévaluée à sa date
    # échéance. Le moteur autorise en plus une « épreuve de confirmation »
    # lorsqu'une maîtrise probable existe mais n'a pas encore été prouvée.
    if (
        progression.nb_erreurs <= 0
        and not quiz_module.revision_due(progression)
        and not quiz_module.besoin_preuve_maitrise(progression)
    ):
        return RedirectResponse("/mes-revisions", status_code=303)

    host = request.client.host if request.client else "inconnu"
    if limite_depassee(f"ia-quiz:user:{utilisateur.id}", 3, 300) or limite_depassee(f"ia-quiz:ip:{host}", 12, 300):
        return RedirectResponse("/mes-revisions?erreur=trop_de_generations", status_code=303)

    niveau = progression.niveau or utilisateur.niveau or "L1"
    if niveau not in quiz_module.NIVEAUX:
        niveau = "L1"

    try:
        tentative = quiz_module.creer_tentative_ciblee(
            session,
            utilisateur,
            progression.matiere,
            niveau,
            progression.notion,
            nb_questions=5,
            progression=progression,
        )
    except quiz_module.QuizValidationError:
        return RedirectResponse("/mes-revisions?erreur=generation_ciblee", status_code=303)

    tache_ia_id = ai_queue.planifier_verification_quiz(tentative.id)
    print(
        f"[AI QUEUE] Route /quiz/cible quiz={tentative.id} tache_ia={tache_ia_id}.",
        flush=True,
    )
    return RedirectResponse(f"/quiz/{tentative.id}", status_code=303)


@router.post("/quiz/examen/generer")
def generer_examen(
    request: Request,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Mode examen : matiere/niveau/difficulte tires au sort par le
    serveur (pas de formulaire a remplir), nombre de questions et duree
    fixes. Meme pipeline de generation/verification que le quiz normal."""
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    host = request.client.host if request.client else "inconnu"
    if limite_depassee(f"ia-quiz:user:{utilisateur.id}", 3, 300) or limite_depassee(f"ia-quiz:ip:{host}", 12, 300):
        return RedirectResponse("/quiz?erreur=trop_de_generations", status_code=303)

    matieres = _matieres_disponibles(session)
    matiere = random.choice(matieres) if matieres else "Culture generale"
    niveau = random.choice(quiz_module.NIVEAUX)
    difficulte = random.choice(quiz_module.DIFFICULTES)

    try:
        tentative = quiz_module.creer_tentative_examen(session, utilisateur, matiere, niveau, difficulte)
    except quiz_module.QuizValidationError:
        return RedirectResponse("/quiz?erreur=generation_invalide", status_code=303)

    tache_ia_id = ai_queue.planifier_verification_quiz(tentative.id)
    print(
        f"[AI QUEUE] Route /quiz/examen/generer quiz={tentative.id} tache_ia={tache_ia_id}.",
        flush=True,
    )
    return RedirectResponse(f"/quiz/{tentative.id}", status_code=303)


@router.post("/quiz/{tentative_id}/soumettre")
async def soumettre_quiz(request: Request, tentative_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    tentative = _tentative_du_proprietaire(session, tentative_id, utilisateur.id)
    if not tentative:
        return RedirectResponse("/quiz", status_code=303)

    if tentative.date_soumission is not None:
        return RedirectResponse(f"/quiz/{tentative.id}", status_code=303)

    try:
        questions = quiz_module.questions(tentative)
    except (ValueError, quiz_module.QuizValidationError) as exc:
        raise HTTPException(status_code=500, detail="Quiz stocke invalide.") from exc

    formulaire = await request.form()
    nb = len(questions)
    reponses_soumises: List[Optional[int]] = []
    confiances_soumises: List[Optional[str]] = []
    for i, question in enumerate(questions):
        valeur = formulaire.get(f"question_{i}")
        confiance = str(formulaire.get(f"confiance_{i}") or "").strip().lower() or None
        if confiance is not None and confiance not in quiz_calibration.NIVEAUX_CONFIANCE:
            raise HTTPException(status_code=400, detail="Niveau de confiance invalide.")

        if valeur is None or valeur == "":
            reponses_soumises.append(None)
            confiances_soumises.append(None)
            continue
        try:
            reponse = int(str(valeur))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Reponse de quiz invalide.") from exc
        if reponse < 0 or reponse >= len(question["choix"]):
            raise HTTPException(status_code=400, detail="Reponse de quiz invalide.")
        reponses_soumises.append(reponse)
        confiances_soumises.append(confiance)

    if tentative.mode_examen and quiz_module.secondes_restantes_examen(tentative) <= 0:
        reponses_soumises = [None] * nb

    try:
        quiz_module.corriger(session, tentative, reponses_soumises)
        quiz_calibration.fusionner_confiances(
            tentative,
            quiz_calibration.normaliser_confiances(
                confiances_soumises,
                len(questions),
            ),
        )
        session.add(tentative)
        session.commit()
        session.refresh(tentative)
    except quiz_module.QuizValidationError as exc:
        raise HTTPException(status_code=400, detail="Reponses de quiz invalides.") from exc

    gamification.enregistrer_action(
        session,
        utilisateur.id,
        "quiz",
        source_type="tentative_quiz",
        source_key=str(tentative.id),
    )
    session.commit()
    return RedirectResponse(f"/quiz/{tentative.id}/resultat", status_code=303)


@router.get("/quiz/{tentative_id}/resultat")
def page_resultat_quiz(request: Request, tentative_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    tentative = _tentative_du_proprietaire(session, tentative_id, utilisateur.id)
    if not tentative or tentative.date_soumission is None:
        return RedirectResponse("/quiz", status_code=303)

    questions_resultat = quiz_module.questions(tentative)
    reponses_resultat = quiz_module.reponses(tentative) or []
    confiances_resultat = quiz_calibration.lire_confiances(tentative)
    diagnostic_confiance = quiz_calibration.diagnostic_confiance(
        tentative,
        questions=questions_resultat,
        reponses=reponses_resultat,
    )
    notions_detectees = []
    progressions_par_question = []
    vus = set()
    for i, question in enumerate(questions_resultat):
        correcte = i < len(reponses_resultat) and reponses_resultat[i] == question.get("index_bonne_reponse")
        if correcte:
            progressions_par_question.append(None)
            continue
        notion = (question.get("notion") or "").strip() or f"Notions générales — {tentative.matiere}"
        progression = session.exec(
            select(ProgressionNotion).where(
                ProgressionNotion.utilisateur_id == utilisateur.id,
                ProgressionNotion.matiere == tentative.matiere,
                ProgressionNotion.notion == notion,
            )
        ).first()
        progressions_par_question.append(progression.id if progression else None)
        if notion in vus:
            continue
        vus.add(notion)
        notions_detectees.append({
            "notion": notion,
            "progression_id": progression.id if progression else None,
        })

    diagnostic_examen = None
    if tentative.mode_examen:
        diagnostic_examen = quiz_module.diagnostic_examen(
            tentative,
            nb_erreurs=sum(
                1
                for i, question in enumerate(questions_resultat)
                if not (
                    i < len(reponses_resultat)
                    and reponses_resultat[i] == question.get("index_bonne_reponse")
                )
            ),
            nb_notions_faibles=len(notions_detectees),
        )

    return templates.TemplateResponse(
        request,
        "quiz_resultat.html",
        {
            "utilisateur": utilisateur,
            "tentative": tentative,
            "questions": questions_resultat,
            "reponses": reponses_resultat,
            "confiances": confiances_resultat,
            "diagnostic_confiance": diagnostic_confiance,
            "notions_detectees": notions_detectees,
            "progressions_par_question": progressions_par_question,
            "diagnostic_examen": diagnostic_examen,
        },
    )


@router.post("/quiz/{tentative_id}/questions/{index_question}/signaler")
def signaler_question_quiz(
    request: Request,
    tentative_id: int,
    index_question: int,
    motif: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection


    tentative = _tentative_du_proprietaire(session, tentative_id, utilisateur.id)
    if not tentative or tentative.date_soumission is None:
        return RedirectResponse("/quiz", status_code=303)

    quiz_module.signaler_question(session, tentative_id, index_question, utilisateur.id, motif)

    return RedirectResponse(f"/quiz/{tentative_id}/resultat?signale=1", status_code=303)
