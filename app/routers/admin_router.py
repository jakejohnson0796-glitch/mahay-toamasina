"""
Surface admin generale : page d'accueil recapitulative, statistiques,
moderation du salon (traitement des signalements), gestion des
utilisateurs (bannissement). Distinct de abonnement_router.py qui gere
deja /admin/abonnements (validation des paiements) — on ne duplique pas
cette partie, juste on y renvoie depuis la page d'accueil admin.
"""
import json
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func

from ..database import get_session
from ..auth import utilisateur_courant
from ..models import (
    Utilisateur, RoleUtilisateur, CercleEtude, MessageCercle, SignalementMessage,
    Document, StatutDocument, TentativeQuiz, AbonnementEtudiant, StatutAbonnementEtudiant,
    SignalementQuestionQuiz,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _admin_requis(request: Request, session: Session) -> Optional[Utilisateur]:
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return None
    return utilisateur


@router.get("/admin")
def page_accueil_admin(request: Request, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    nb_signalements_en_attente = len(
        session.exec(select(SignalementMessage).where(SignalementMessage.traite == False)).all()  # noqa: E712
    )
    nb_signalements_quiz_en_attente = len(
        session.exec(select(SignalementQuestionQuiz).where(SignalementQuestionQuiz.traite == False)).all()  # noqa: E712
    )
    nb_abonnements_en_attente = len(
        session.exec(
            select(AbonnementEtudiant).where(AbonnementEtudiant.statut == StatutAbonnementEtudiant.EN_ATTENTE)
        ).all()
    )

    return templates.TemplateResponse(
        request,
        "admin_index.html",
        {
            "utilisateur": admin,
            "nb_signalements_en_attente": nb_signalements_en_attente,
            "nb_signalements_quiz_en_attente": nb_signalements_quiz_en_attente,
            "nb_abonnements_en_attente": nb_abonnements_en_attente,
        },
    )


@router.get("/admin/stats")
def page_stats(request: Request, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    nb_etudiants = session.exec(
        select(func.count()).select_from(Utilisateur).where(Utilisateur.role == RoleUtilisateur.ETUDIANT)
    ).one()
    nb_essai_actif = session.exec(
        select(func.count()).select_from(AbonnementEtudiant).where(AbonnementEtudiant.statut == StatutAbonnementEtudiant.ESSAI)
    ).one()
    nb_abonnes_actifs = session.exec(
        select(func.count()).select_from(AbonnementEtudiant).where(AbonnementEtudiant.statut == StatutAbonnementEtudiant.ACTIF)
    ).one()
    nb_demandes_en_attente = session.exec(
        select(func.count()).select_from(AbonnementEtudiant).where(AbonnementEtudiant.statut == StatutAbonnementEtudiant.EN_ATTENTE)
    ).one()
    nb_documents_approuves = session.exec(
        select(func.count()).select_from(Document).where(Document.statut == StatutDocument.APPROUVE)
    ).one()
    nb_documents_en_attente = session.exec(
        select(func.count()).select_from(Document).where(Document.statut == StatutDocument.EN_ATTENTE)
    ).one()
    nb_quiz_realises = session.exec(
        select(func.count()).select_from(TentativeQuiz).where(TentativeQuiz.date_soumission.is_not(None))
    ).one()
    nb_cercles = session.exec(select(func.count()).select_from(CercleEtude)).one()
    nb_signalements_en_attente = session.exec(
        select(func.count()).select_from(SignalementMessage).where(SignalementMessage.traite == False)  # noqa: E712
    ).one()
    nb_signalements_quiz_en_attente = session.exec(
        select(func.count()).select_from(SignalementQuestionQuiz).where(SignalementQuestionQuiz.traite == False)  # noqa: E712
    ).one()

    # Matieres les plus demandees en quiz (top 5), calcule en Python sur un
    # petit GROUP BY — volume attendu trop faible pour justifier plus.
    lignes_matieres = session.exec(
        select(TentativeQuiz.matiere, func.count()).group_by(TentativeQuiz.matiere).order_by(func.count().desc())
    ).all()

    return templates.TemplateResponse(
        request,
        "admin_stats.html",
        {
            "utilisateur": admin,
            "nb_etudiants": nb_etudiants,
            "nb_essai_actif": nb_essai_actif,
            "nb_abonnes_actifs": nb_abonnes_actifs,
            "nb_demandes_en_attente": nb_demandes_en_attente,
            "nb_documents_approuves": nb_documents_approuves,
            "nb_documents_en_attente": nb_documents_en_attente,
            "nb_quiz_realises": nb_quiz_realises,
            "nb_cercles": nb_cercles,
            "nb_signalements_en_attente": nb_signalements_en_attente,
            "nb_signalements_quiz_en_attente": nb_signalements_quiz_en_attente,
            "top_matieres": lignes_matieres[:5],
        },
    )


@router.get("/admin/moderation-salon")
def page_moderation_salon(request: Request, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    lignes = session.exec(
        select(SignalementMessage, MessageCercle, Utilisateur, CercleEtude)
        .where(SignalementMessage.traite == False)  # noqa: E712
        .where(SignalementMessage.message_id == MessageCercle.id)
        .where(SignalementMessage.signale_par_id == Utilisateur.id)
        .where(MessageCercle.cercle_id == CercleEtude.id)
        .order_by(SignalementMessage.date_signalement.desc())
    ).all()

    signalements = [
        {
            "signalement": s,
            "message": m,
            "signale_par": u,
            "cercle": c,
            "message_deja_supprime": m.supprime,
        }
        for s, m, u, c in lignes
    ]

    return templates.TemplateResponse(
        request,
        "admin_moderation_salon.html",
        {"utilisateur": admin, "signalements": signalements},
    )


@router.post("/admin/moderation-salon/{signalement_id}/supprimer-message")
def moderer_supprimer_message(request: Request, signalement_id: int, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    signalement = session.get(SignalementMessage, signalement_id)
    if signalement:
        message = session.get(MessageCercle, signalement.message_id)
        if message:
            message.supprime = True
            session.add(message)
        signalement.traite = True
        session.add(signalement)
        session.commit()

    return RedirectResponse("/admin/moderation-salon", status_code=303)


@router.post("/admin/moderation-salon/{signalement_id}/rejeter")
def moderer_rejeter_signalement(request: Request, signalement_id: int, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    signalement = session.get(SignalementMessage, signalement_id)
    if signalement:
        signalement.traite = True
        session.add(signalement)
        session.commit()

    return RedirectResponse("/admin/moderation-salon", status_code=303)


@router.get("/admin/moderation-quiz")
def page_moderation_quiz(request: Request, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    lignes = session.exec(
        select(SignalementQuestionQuiz, TentativeQuiz, Utilisateur)
        .where(SignalementQuestionQuiz.traite == False)  # noqa: E712
        .where(SignalementQuestionQuiz.tentative_id == TentativeQuiz.id)
        .where(SignalementQuestionQuiz.signale_par_id == Utilisateur.id)
        .order_by(SignalementQuestionQuiz.date_signalement.desc())
    ).all()

    signalements = []
    for s, tentative, signale_par in lignes:
        try:
            question = json.loads(tentative.questions_json)[s.index_question]
        except (json.JSONDecodeError, IndexError, KeyError):
            question = None
        signalements.append({
            "signalement": s,
            "tentative": tentative,
            "signale_par": signale_par,
            "question": question,
        })

    return templates.TemplateResponse(
        request,
        "admin_moderation_quiz.html",
        {"utilisateur": admin, "signalements": signalements},
    )


@router.post("/admin/moderation-quiz/{signalement_id}/traiter")
def moderer_traiter_signalement_quiz(request: Request, signalement_id: int, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    signalement = session.get(SignalementQuestionQuiz, signalement_id)
    if signalement:
        signalement.traite = True
        session.add(signalement)
        session.commit()

    return RedirectResponse("/admin/moderation-quiz", status_code=303)


@router.get("/admin/utilisateurs")
def page_utilisateurs(request: Request, q: Optional[str] = None, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    requete = select(Utilisateur).order_by(Utilisateur.date_creation.desc())
    if q:
        terme = f"%{q.strip()}%"
        requete = requete.where((Utilisateur.nom.ilike(terme)) | (Utilisateur.telephone.ilike(terme)))
    utilisateurs = session.exec(requete).all()

    return templates.TemplateResponse(
        request,
        "admin_utilisateurs.html",
        {"utilisateur": admin, "utilisateurs": utilisateurs, "recherche": q or ""},
    )


@router.post("/admin/utilisateurs/{utilisateur_id}/bannir")
def bannir_utilisateur(request: Request, utilisateur_id: int, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    cible = session.get(Utilisateur, utilisateur_id)
    # Un admin ne peut pas se bannir lui-meme (garde-fou simple pour eviter
    # de se retrouver bloque hors de l'interface admin par erreur).
    if cible and cible.id != admin.id:
        cible.banni = True
        session.add(cible)
        session.commit()

    return RedirectResponse("/admin/utilisateurs", status_code=303)


@router.post("/admin/utilisateurs/{utilisateur_id}/debannir")
def debannir_utilisateur(request: Request, utilisateur_id: int, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    cible = session.get(Utilisateur, utilisateur_id)
    if cible:
        cible.banni = False
        session.add(cible)
        session.commit()

    return RedirectResponse("/admin/utilisateurs", status_code=303)
