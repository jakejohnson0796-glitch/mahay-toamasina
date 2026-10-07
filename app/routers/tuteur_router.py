from fastapi import APIRouter, Request, Depends, Form, BackgroundTasks
from typing import Optional
from fastapi.responses import RedirectResponse
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..auth import utilisateur_courant
from ..dependencies import acces_ia_ou_redirection
from ..models import SessionTuteur, ProgressionNotion
from ..ia_transport import normaliser_structure_tuteur
from .. import ai_quiz
from ..rate_limit import limite_depassee
from .. import quiz as quiz_module
from .. import gamification

router = APIRouter()

NB_HISTORIQUE_AFFICHE = 10


@router.get("/tuteur")
def page_tuteur(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    historique = session.exec(
        select(SessionTuteur)
        .where(SessionTuteur.utilisateur_id == utilisateur.id)
        .order_by(SessionTuteur.date_creation.desc())
        .limit(NB_HISTORIQUE_AFFICHE)
    ).all()

    notions = quiz_module.notions_a_revoir(session, utilisateur.id, limit=8)

    return templates.TemplateResponse(
        request,
        "tuteur.html",
        {
            "utilisateur": utilisateur,
            "historique": historique,
            "notions_a_revoir": notions,
        },
    )


@router.post("/tuteur/demander")
def demander_tuteur(
    request: Request,
    background_tasks: BackgroundTasks,
    question: str = Form(...),
    progression_id: Optional[int] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    host = request.client.host if request.client else "inconnu"
    if limite_depassee(f"ia-tuteur:user:{utilisateur.id}", 10, 300) or limite_depassee(f"ia-tuteur:ip:{host}", 30, 300):
        return RedirectResponse("/tuteur?erreur=trop_de_questions", status_code=303)

    question = question.strip()[:4000]
    if not question:
        return RedirectResponse("/tuteur?erreur=question_requise", status_code=303)

    progression = None
    if progression_id:
        progression = session.get(ProgressionNotion, progression_id)
        if not progression or progression.utilisateur_id != utilisateur.id or progression.nb_erreurs <= 0:
            progression = None

    reponse = ai_quiz.generer_reponse_tuteur(
        question,
        notion=progression.notion if progression else None,
        matiere=progression.matiere if progression else None,
        verifier=False,
    )
    statut_verification = reponse.pop("_statut_verification", "terminee")
    erreur_verification = reponse.pop("_erreur_verification", None)
    reponse.pop("_verification_ok", None)

    # MODIF : canonisation finale avant tout stockage, même en cas de secours
    # ou d'arbitrage multi-modèles partiel.
    reponse = normaliser_structure_tuteur(reponse)

    session_tuteur = SessionTuteur(
        utilisateur_id=utilisateur.id,
        notion=progression.notion if progression else None,
        progression_id=progression.id if progression else None,
        question=question,
        explication=reponse["explication"],
        exemple=reponse["exemple"],
        exercice=reponse["exercice"],
        correction=reponse["correction"],
        statut_verification_ia=statut_verification,
        erreur_verification_ia=erreur_verification,
    )
    session.add(session_tuteur)
    session.flush()
    gamification.enregistrer_action(
        session,
        utilisateur.id,
        "tuteur",
        source_type="session_tuteur",
        source_key=str(session_tuteur.id),
    )
    session.commit()
    session.refresh(session_tuteur)

    # La réponse initiale est livrée immédiatement. La vérification
    # multi-modèles s'exécute après l'envoi HTTP et mettra à jour la session ;
    # la page de réponse la récupère via son polling existant.
    background_tasks.add_task(
        ai_quiz.verifier_session_tuteur_en_arriere_plan,
        session_tuteur.id,
    )

    return RedirectResponse(f"/tuteur/{session_tuteur.id}", status_code=303)


@router.get("/tuteur/{session_id}/statut")
def statut_tuteur(request: Request, session_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return JSONResponse({"statut": "non_autorise"}, status_code=401)

    session_tuteur = session.get(SessionTuteur, session_id)
    if not session_tuteur or session_tuteur.utilisateur_id != utilisateur.id:
        return JSONResponse({"statut": "introuvable"}, status_code=404)

    # MODIF : l'API transmet désormais uniquement le texte brut de la
    # réponse IA ; le rendu Markdown/KaTeX est réalisé dans le navigateur.
    contenu = normaliser_structure_tuteur({
        "explication": session_tuteur.explication,
        "exemple": session_tuteur.exemple,
        "exercice": session_tuteur.exercice,
        "correction": session_tuteur.correction,
    })

    def rendu(champ: str) -> str:
        return contenu.get(champ, "")

    return {
        "statut": session_tuteur.statut_verification_ia,
        "erreur": session_tuteur.erreur_verification_ia,
        "date_verification": (
            session_tuteur.date_verification_ia.isoformat()
            if session_tuteur.date_verification_ia
            else None
        ),
        "contenu": {
            "explication": rendu("explication"),
            "exemple": rendu("exemple"),
            "exercice": rendu("exercice"),
            "correction": rendu("correction"),
        },
    }


@router.get("/tuteur/{session_id}")
def page_reponse_tuteur(request: Request, session_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    session_tuteur = session.get(SessionTuteur, session_id)
    if not session_tuteur or session_tuteur.utilisateur_id != utilisateur.id:
        return RedirectResponse("/tuteur", status_code=303)

    # MODIF : le template reçoit aussi les contenus canonisés pour éviter
    # que les anciennes sessions affichent des marqueurs de transport.
    session_vue = dict(
        utilisateur=utilisateur,
        session_tuteur=session_tuteur,
        contenu_tuteur=normaliser_structure_tuteur({
            "explication": session_tuteur.explication,
            "exemple": session_tuteur.exemple,
            "exercice": session_tuteur.exercice,
            "correction": session_tuteur.correction,
        }),
    )
    return templates.TemplateResponse(
        request,
        "tuteur_reponse.html",
        session_vue,
    )
