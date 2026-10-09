"""Espace personnel « Mes révisions »."""
from datetime import datetime
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select, func

from ..auth import utilisateur_courant
from ..database import get_session
from ..models import ConsultationDocument, Document, MissionApprentissage, ProgressionNotion, SessionTuteur, TentativeQuiz, StatutDocument
from ..templating import templates
from .. import dashboard as dashboard_module
from .. import quiz as quiz_module
from .. import gamification
from .. import knowledge_map
from .. import learning_session
from .. import adaptive_learning

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
    """Reprend la mission courante ou prépare l'étape suivante."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    progressions = session.exec(
        select(ProgressionNotion)
        .where(ProgressionNotion.utilisateur_id == utilisateur.id)
        .where(ProgressionNotion.nb_questions > 0)
        .order_by(ProgressionNotion.score_maitrise.asc(), ProgressionNotion.date_maj.desc())
    ).all()
    par_id = {int(p.id): p for p in progressions if p.id is not None}
    carte = knowledge_map.construire_carte(progressions)
    etat = session.exec(
        select(MissionApprentissage).where(MissionApprentissage.utilisateur_id == utilisateur.id)
    ).first()

    def mission_pour(progression):
        cible = {
            "id": progression.id,
            "matiere": progression.matiere,
            "notion": progression.notion,
            "score": progression.score_maitrise,
        }
        return learning_session.construire_mission({"prochaine": cible}, progressions)

    if etat and etat.statut == "active":
        progression = par_id.get(int(etat.progression_id))
        if progression is None:
            progression = session.get(ProgressionNotion, etat.progression_id)
        if progression and progression.utilisateur_id == utilisateur.id:
            mission = adaptive_learning.appliquer_etat(mission_pour(progression), etat)
        else:
            mission = learning_session.construire_mission(carte, progressions)
    elif etat and etat.statut == "terminee":
        cible_suivante = adaptive_learning.choisir_prochaine_notion(
            carte,
            progressions,
            exclure_id=etat.progression_id,
        )
        progression = par_id.get(int(cible_suivante["id"])) if cible_suivante else None
        if progression is not None:
            base = mission_pour(progression)
            etat.progression_id = int(progression.id)
            etat.etape = "comprendre" if base.get("action_principale") == "tuteur" else "pratiquer"
            etat.statut = "active"
            etat.nb_tentatives = 0
            etat.dernier_score = None
            etat.derniere_tentative_id = None
            etat.derniere_session_tuteur_id = None
            etat.dernier_feedback = None
            etat.date_fin = None
            etat.date_maj = datetime.utcnow()
            session.add(etat)
            session.commit()
            session.refresh(etat)
            mission = adaptive_learning.appliquer_etat(base, etat)
        else:
            mission = adaptive_learning.vue_toutes_notions_confirmees()
    else:
        cible = carte.get("prochaine")
        mission = learning_session.construire_mission(carte, progressions)
        if cible:
            progression = par_id.get(int(cible.get("id") or 0))
            if progression is not None:
                etape = "comprendre" if mission.get("action_principale") == "tuteur" else "pratiquer"
                etat = MissionApprentissage(
                    utilisateur_id=utilisateur.id,
                    progression_id=progression.id,
                    etape=etape,
                    statut="active",
                )
                session.add(etat)
                session.commit()
                session.refresh(etat)
                mission = adaptive_learning.appliquer_etat(mission, etat)

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
