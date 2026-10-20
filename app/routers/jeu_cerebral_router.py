"""Routes du jeu de défis cérébraux de MITARIDALA."""
import json
import logging
import random
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from .. import gamification, jeu_cerebral
from ..auth import utilisateur_courant
from ..csrf import verifier_csrf
from ..database import get_session
from ..dependencies import acces_ia_ou_redirection
from ..models import JeuCerebralSession
from ..rate_limit import limite_depassee
from ..templating import templates

router = APIRouter()
logger = logging.getLogger(__name__)


def _charger_questions(partie: JeuCerebralSession) -> list[dict]:
    try:
        valeur = json.loads(partie.questions_json or "[]")
        return valeur if isinstance(valeur, list) else []
    except (TypeError, ValueError):
        return []


def _charger_recommandation(partie: JeuCerebralSession) -> dict:
    try:
        valeur = json.loads(partie.recommandation_json or "{}")
        return valeur if isinstance(valeur, dict) else {}
    except (TypeError, ValueError):
        return {}


def _partie_du_proprietaire(
    session: Session,
    partie_id: int,
    utilisateur_id: int,
) -> Optional[JeuCerebralSession]:
    partie = session.get(JeuCerebralSession, partie_id)
    if not partie or partie.utilisateur_id != utilisateur_id:
        return None
    return partie


@router.get("/jeu-cerebral")
def page_jeu_cerebral(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    sessions_progression = session.exec(
        select(JeuCerebralSession)
        .where(JeuCerebralSession.utilisateur_id == utilisateur.id)
        .where(JeuCerebralSession.date_fin.is_not(None))
        .order_by(JeuCerebralSession.date_creation.desc())
        .limit(20)
    ).all()
    # La page conserve une liste courte, mais l'analyse de progression dispose
    # d'un historique plus large pour ne pas surinterpréter une seule session.
    historique = sessions_progression[:8]
    profil = jeu_cerebral.profil_pour_ia(sessions_progression, langue=None)
    progression_notion = jeu_cerebral.progression_sur_plusieurs_sessions(sessions_progression)
    moyenne = profil.get("moyenne_recente")
    historique_affiche = [
        {"partie": partie, "theme": jeu_cerebral.obtenir_theme(partie.theme_id)}
        for partie in historique
    ]
    return templates.TemplateResponse(
        request,
        "jeu_cerebral.html",
        {
            "utilisateur": utilisateur,
            "themes": jeu_cerebral.THEMES,
            "historique": historique,
            "historique_affiche": historique_affiche,
            "profil": profil,
            "progression_notion": progression_notion,
            "moyenne_recente": moyenne,
        },
    )


@router.post("/jeu-cerebral/demarrer")
def demarrer_jeu_cerebral(
    request: Request,
    theme: str = Form("aleatoire"),
    langue: str = Form("fr"),
    chronometre: str = Form(""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    host = request.client.host if request.client else "inconnu"
    if (
        limite_depassee(f"jeu-cerebral:user:{utilisateur.id}", 5, 300)
        or limite_depassee(f"jeu-cerebral:ip:{host}", 18, 300)
    ):
        return RedirectResponse("/jeu-cerebral?erreur=rythme", status_code=303)

    langue = langue if langue in {"fr", "mg"} else "fr"
    if theme == "aleatoire":
        theme_id = random.choice(jeu_cerebral.THEMES)["id"]
    elif theme in jeu_cerebral.THEMES_PAR_ID:
        theme_id = theme
    else:
        return RedirectResponse("/jeu-cerebral?erreur=theme", status_code=303)

    historique = session.exec(
        select(JeuCerebralSession)
        .where(JeuCerebralSession.utilisateur_id == utilisateur.id)
        .where(JeuCerebralSession.date_fin.is_not(None))
        .order_by(JeuCerebralSession.date_creation.desc())
        .limit(20)
    ).all()
    profil = jeu_cerebral.profil_pour_ia(historique, langue=langue)
    difficulte = profil["difficulte_depart"]

    # Le mini-jeu reste accessible. Si l'accès IA est expiré ou non disponible,
    # la banque locale bilingue prend le relais et la page l'indique clairement.
    redirection_ia = acces_ia_ou_redirection(utilisateur, session)
    utiliser_ia = redirection_ia is None
    questions, source = jeu_cerebral.generer_banque_questions(
        theme_id,
        langue,
        profil,
        utiliser_ia=utiliser_ia,
    )
    if len(questions) < jeu_cerebral.NB_QUESTIONS_SESSION:
        logger.error("Banque de jeu cérébral insuffisante pour le thème %s.", theme_id)
        return RedirectResponse("/jeu-cerebral?erreur=questions", status_code=303)

    etat = jeu_cerebral.etat_initial(questions, difficulte)
    etat["langue"] = langue
    # Le chrono est un objectif facultatif côté interface, jamais une pénalité de score.
    etat["chrono_actif"] = str(chronometre).strip() == "1"
    partie = JeuCerebralSession(
        utilisateur_id=utilisateur.id,
        theme_id=theme_id,
        langue=langue,
        source_generation=source if utiliser_ia else "local",
        difficulte_initiale=difficulte,
        nb_questions=jeu_cerebral.NB_QUESTIONS_SESSION,
        questions_json=json.dumps(questions, ensure_ascii=False),
        reponses_json=json.dumps(etat, ensure_ascii=False),
    )
    session.add(partie)
    session.commit()
    session.refresh(partie)
    return RedirectResponse(f"/jeu-cerebral/{partie.id}", status_code=303)


@router.get("/jeu-cerebral/{partie_id}/resultat")
def resultat_jeu_cerebral(
    request: Request,
    partie_id: int,
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    partie = _partie_du_proprietaire(session, partie_id, utilisateur.id)
    if not partie:
        return RedirectResponse("/jeu-cerebral", status_code=303)
    if partie.date_fin is None:
        return RedirectResponse(f"/jeu-cerebral/{partie.id}", status_code=303)

    questions = _charger_questions(partie)
    etat = jeu_cerebral.lire_etat(partie.reponses_json)
    recommendation = _charger_recommandation(partie)
    sessions_progression = session.exec(
        select(JeuCerebralSession)
        .where(JeuCerebralSession.utilisateur_id == utilisateur.id)
        .where(JeuCerebralSession.date_fin.is_not(None))
        .where(JeuCerebralSession.langue == partie.langue)
        .order_by(JeuCerebralSession.date_creation.desc())
        .limit(20)
    ).all()
    progression_notion = jeu_cerebral.progression_sur_plusieurs_sessions(
        sessions_progression,
        langue=partie.langue,
    )
    ordre = [int(i) for i in etat.get("ordre", [])]
    reponses = list(etat.get("reponses") or [])
    corrections = []
    for index in ordre:
        if not 0 <= index < len(questions):
            continue
        question = questions[index]
        choisi = reponses[index] if index < len(reponses) else None
        bonne = question.get("index_bonne_reponse")
        corrections.append({
            "numero": len(corrections) + 1,
            "question": question.get("question", ""),
            "choix": question.get("choix") or [],
            "reponse_choisie": choisi,
            "reponse_correcte": bonne,
            "correcte": choisi == bonne,
            "explication": question.get("explication", ""),
            "notion": question.get("notion", ""),
        })

    return templates.TemplateResponse(
        request,
        "jeu_cerebral_resultat.html",
        {
            "utilisateur": utilisateur,
            "partie": partie,
            "theme": jeu_cerebral.obtenir_theme(partie.theme_id),
            "recommandation": recommendation,
            "progression_notion": progression_notion,
            "corrections": corrections,
            "langue": partie.langue,
        },
    )


@router.get("/jeu-cerebral/{partie_id}")
def page_session_jeu_cerebral(
    request: Request,
    partie_id: int,
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    partie = _partie_du_proprietaire(session, partie_id, utilisateur.id)
    if not partie:
        return RedirectResponse("/jeu-cerebral", status_code=303)
    if partie.date_fin is not None:
        return RedirectResponse(f"/jeu-cerebral/{partie.id}/resultat", status_code=303)

    questions = _charger_questions(partie)
    etat = jeu_cerebral.lire_etat(partie.reponses_json)
    ordre = [int(i) for i in etat.get("ordre", [])]
    if not questions or not ordre:
        return RedirectResponse("/jeu-cerebral?erreur=questions", status_code=303)

    index_question = ordre[-1]
    reponses = list(etat.get("reponses") or [])
    if index_question < 0 or index_question >= len(questions):
        return RedirectResponse("/jeu-cerebral?erreur=questions", status_code=303)
    if index_question < len(reponses) and reponses[index_question] is not None:
        return RedirectResponse(f"/jeu-cerebral/{partie.id}/resultat", status_code=303)

    question = questions[index_question]
    difficulte = question.get("difficulte", "Moyen")
    labels_difficulte = (
        {"Facile": "En douceur", "Moyen": "À ton rythme", "Difficile": "Petit défi"}
        if partie.langue == "fr"
        else {"Facile": "Amim-pitoniana", "Moyen": "Amin'ny hafainganam-pandehanao", "Difficile": "Fanamby kely"}
    )
    retour = etat.get("dernier_feedback")
    if retour and 0 <= int(retour.get("question_index", -1)) < len(questions):
        ancienne = questions[int(retour["question_index"])]
        choix_anciens = ancienne.get("choix") or []
        index_bonne = ancienne.get("index_bonne_reponse")
        index_choisi = reponses[int(retour["question_index"])] if int(retour["question_index"]) < len(reponses) else None
        retour = {
            **retour,
            "question": ancienne.get("question", ""),
            "explication": ancienne.get("explication", ""),
            "reponse_correcte": choix_anciens[index_bonne] if isinstance(index_bonne, int) and 0 <= index_bonne < len(choix_anciens) else "",
            "reponse_choisie": choix_anciens[index_choisi] if isinstance(index_choisi, int) and 0 <= index_choisi < len(choix_anciens) else "",
        }

    return templates.TemplateResponse(
        request,
        "jeu_cerebral_session.html",
        {
            "utilisateur": utilisateur,
            "partie": partie,
            "theme": jeu_cerebral.obtenir_theme(partie.theme_id),
            "question": question,
            "index_question": index_question,
            "numero_question": len(ordre),
            "total_questions": partie.nb_questions,
            "progression_pct": min(100, round((len(ordre) - 1) * 100 / partie.nb_questions)),
            "label_difficulte": labels_difficulte.get(difficulte, labels_difficulte["Moyen"]),
            "niveau_index": {"Facile": 0, "Moyen": 1, "Difficile": 2}.get(difficulte, 1),
            "chrono_actif": bool(etat.get("chrono_actif", False)),
            "retour": retour,
            "langue": partie.langue,
        },
    )


@router.post("/jeu-cerebral/{partie_id}/repondre")
def repondre_jeu_cerebral(
    request: Request,
    partie_id: int,
    index_question: int = Form(...),
    reponse: int = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    partie = _partie_du_proprietaire(session, partie_id, utilisateur.id)
    if not partie:
        return RedirectResponse("/jeu-cerebral", status_code=303)
    if partie.date_fin is not None:
        return RedirectResponse(f"/jeu-cerebral/{partie.id}/resultat", status_code=303)

    questions = _charger_questions(partie)
    etat = jeu_cerebral.lire_etat(partie.reponses_json)
    try:
        nouvel_etat, _correcte, _suivante = jeu_cerebral.enregistrer_reponse(
            questions,
            etat,
            index_question,
            reponse,
            langue=partie.langue,
        )
    except (ValueError, TypeError, IndexError) as erreur:
        logger.info("Réponse de jeu cérébral refusée pour partie %s (%s).", partie_id, type(erreur).__name__)
        return RedirectResponse(f"/jeu-cerebral/{partie.id}", status_code=303)

    partie.reponses_json = json.dumps(nouvel_etat, ensure_ascii=False)
    ordre = [int(i) for i in nouvel_etat.get("ordre", [])]
    if nouvel_etat.get("termine"):
        recommendation = jeu_cerebral.construire_recommandation(
            partie.theme_id,
            questions,
            nouvel_etat,
        )
        recommendation["langue"] = partie.langue
        partie.score = int(recommendation["score"])
        partie.bonnes_reponses = int(recommendation["bonnes_reponses"])
        partie.recommandation_json = json.dumps(recommendation, ensure_ascii=False)
        partie.date_fin = datetime.utcnow()
        gamification.enregistrer_action(
            session,
            utilisateur.id,
            "revision",
            source_type="jeu_cerebral",
            source_key=str(partie.id),
        )
    session.add(partie)
    session.commit()

    if partie.date_fin is not None:
        return RedirectResponse(f"/jeu-cerebral/{partie.id}/resultat", status_code=303)
    return RedirectResponse(f"/jeu-cerebral/{partie.id}", status_code=303)
