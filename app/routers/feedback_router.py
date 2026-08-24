"""
Feedback utilisateurs : formulaire de notation (/feedback), avis publics,
reponses de l'administration (/admin/feedback).

Reutilise integralement l'infrastructure existante plutot que d'en
recreer une : verifier_csrf (csrf.py), limite_depassee (rate_limit.py),
Notification/TypeNotification (models.py, deja concu pour ce chantier —
voir sa docstring), et le meme garde-fou admin local que les autres
routers admin (documents_router.py, admin_router.py, faq_router.py).
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..auth import utilisateur_courant
from ..rate_limit import limite_depassee
from ..models import (
    Feedback, ReponseFeedback, CategorieFeedback, StatutFeedback,
    Utilisateur, RoleUtilisateur, Notification, TypeNotification,
    CategorieFAQ,
)
from ..aide_avis_data import donnees_faq, donnees_avis

router = APIRouter()

LONGUEUR_MAX_COMMENTAIRE = 1000


def _ip_client(request: Request) -> str:
    return request.client.host if request.client else "inconnu"


def _admin_requis(request: Request, session: Session) -> Optional[Utilisateur]:
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return None
    return utilisateur


def _creer_notification_reponse(session: Session, feedback: Feedback) -> None:
    session.add(Notification(
        destinataire_id=feedback.utilisateur_id,
        type_notification=TypeNotification.REPONSE_FEEDBACK,
        contenu="Mahay a repondu a votre feedback.",
    ))
    session.commit()


# ============================================================
# Formulaire utilisateur + avis publics
# ============================================================

@router.get("/feedback")
def page_feedback(
    request: Request,
    categorie_avis: Optional[CategorieFeedback] = None,
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)

    avis_affiches, note_moyenne, total_avis = donnees_avis(session, categorie_avis)

    mon_feedback_recent = None
    if utilisateur:
        mon_feedback_recent = session.exec(
            select(Feedback)
            .where(Feedback.utilisateur_id == utilisateur.id)
            .order_by(Feedback.date_creation.desc())
        ).first()

    # Etape 13 (brief refonte visuelle) : voir le commentaire equivalent
    # dans faq_router.py -- meme interface fusionnee des deux cotes,
    # colonne FAQ peuplee ici sans filtre (le lien "Filtrer" de cette
    # colonne pointe vers /faq?q=...&categorie=... pour rester sur une
    # seule URL canonique par filtre).
    questions = donnees_faq(session, None, None)

    return templates.TemplateResponse(
        request,
        "aide_avis.html",
        {
            "utilisateur": utilisateur,
            "avis_affiches": avis_affiches,
            "note_moyenne": note_moyenne,
            "total_avis": total_avis,
            "categories_avis": list(CategorieFeedback),
            "categorie_avis_filtre": categorie_avis.value if categorie_avis else "",
            "longueur_max": LONGUEUR_MAX_COMMENTAIRE,
            "mon_feedback_recent": mon_feedback_recent,
            "questions": questions,
            "categories_faq": list(CategorieFAQ),
            "q": "",
            "categorie_filtre": "",
        },
    )


@router.post("/feedback")
def envoyer_feedback(
    request: Request,
    note: int = Form(...),
    commentaire: str = Form(...),
    categorie: CategorieFeedback = Form(CategorieFeedback.GENERAL),
    est_public: Optional[str] = Form(None),  # case a cocher HTML : present ou absent
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    # --- Rate limiting : reutilise rate_limit.py (pas de deuxieme systeme) ---
    if limite_depassee(f"feedback:user:{utilisateur.id}", max_tentatives=5, fenetre_secondes=3600) or \
       limite_depassee(f"feedback:ip:{_ip_client(request)}", max_tentatives=10, fenetre_secondes=3600):
        return RedirectResponse("/feedback?erreur=trop_de_tentatives", status_code=303)

    # --- Validation backend (jamais se fier uniquement au frontend) ---
    if note < 1 or note > 5:
        return RedirectResponse("/feedback?erreur=note_invalide", status_code=303)

    commentaire = commentaire.strip()
    if not commentaire:
        return RedirectResponse("/feedback?erreur=commentaire_requis", status_code=303)
    if len(commentaire) > LONGUEUR_MAX_COMMENTAIRE:
        return RedirectResponse("/feedback?erreur=commentaire_trop_long", status_code=303)

    # --- Protection contre un double-clic accidentel envoyant deux fois
    # le meme avis : si le dernier feedback de cet utilisateur, dans les
    # 30 dernieres secondes, a exactement le meme commentaire et la meme
    # note, on ne le reinsere pas silencieusement. ---
    il_y_a_30s = datetime.utcnow().timestamp() - 30
    dernier = session.exec(
        select(Feedback)
        .where(Feedback.utilisateur_id == utilisateur.id)
        .order_by(Feedback.date_creation.desc())
    ).first()
    if dernier and dernier.commentaire == commentaire and dernier.note == note \
       and dernier.date_creation.timestamp() > il_y_a_30s:
        return RedirectResponse("/feedback?envoye=1", status_code=303)

    feedback = Feedback(
        utilisateur_id=utilisateur.id,
        note=note,
        commentaire=commentaire,
        categorie=categorie,
        est_public=bool(est_public),
    )
    session.add(feedback)
    session.commit()
    return RedirectResponse("/feedback?envoye=1", status_code=303)


@router.get("/feedback/mes-avis")
def mes_avis(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    mes_feedbacks = session.exec(
        select(Feedback)
        .where(Feedback.utilisateur_id == utilisateur.id)
        .order_by(Feedback.date_creation.desc())
    ).all()
    ids = [f.id for f in mes_feedbacks]
    reponses_par_feedback = {}
    if ids:
        reponses = session.exec(
            select(ReponseFeedback).where(ReponseFeedback.feedback_id.in_(ids))
        ).all()
        reponses_par_feedback = {r.feedback_id: r for r in reponses}

    mes_avis_affiches = [
        {"feedback": f, "reponse": reponses_par_feedback.get(f.id)}
        for f in mes_feedbacks
    ]

    return templates.TemplateResponse(
        request,
        "mes_avis.html",
        {"utilisateur": utilisateur, "mes_avis_affiches": mes_avis_affiches},
    )


# ============================================================
# Administration des feedbacks
# ============================================================

@router.get("/admin/feedback")
def admin_liste_feedback(
    request: Request,
    q: Optional[str] = None,
    note: Optional[int] = None,
    categorie: Optional[CategorieFeedback] = None,
    statut: Optional[StatutFeedback] = None,
    session: Session = Depends(get_session),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    requete = select(Feedback)
    if note:
        requete = requete.where(Feedback.note == note)
    if categorie:
        requete = requete.where(Feedback.categorie == categorie)
    if statut:
        requete = requete.where(Feedback.statut == statut)
    if q:
        requete = requete.where(Feedback.commentaire.ilike(f"%{q.strip()}%"))
    feedbacks = session.exec(requete.order_by(Feedback.date_creation.desc())).all()

    ids = [f.id for f in feedbacks]
    reponses_par_feedback = {}
    if ids:
        reponses = session.exec(
            select(ReponseFeedback).where(ReponseFeedback.feedback_id.in_(ids))
        ).all()
        reponses_par_feedback = {r.feedback_id: r for r in reponses}

    utilisateurs_par_id = {
        u.id: u for u in session.exec(select(Utilisateur)).all()
    } if feedbacks else {}

    feedbacks_affiches = [
        {
            "feedback": f,
            "auteur": utilisateurs_par_id.get(f.utilisateur_id),
            "reponse": reponses_par_feedback.get(f.id),
        }
        for f in feedbacks
    ]

    # --- Statistiques du tableau de bord admin (Partie 9 du brief) ---
    tous_feedbacks = session.exec(select(Feedback)).all()
    total = len(tous_feedbacks)
    note_moyenne = round(sum(f.note for f in tous_feedbacks) / total, 1) if total else 0
    repartition = {n: len([f for f in tous_feedbacks if f.note == n]) for n in range(5, 0, -1)}
    ids_avec_reponse = {
        r.feedback_id for r in session.exec(select(ReponseFeedback)).all()
    }
    nb_sans_reponse = len([f for f in tous_feedbacks if f.id not in ids_avec_reponse and f.statut != StatutFeedback.MASQUE])

    return templates.TemplateResponse(
        request,
        "admin_feedback.html",
        {
            "utilisateur": admin,
            "feedbacks_affiches": feedbacks_affiches,
            "categories": list(CategorieFeedback),
            "statuts": list(StatutFeedback),
            "q": q or "",
            "note_filtre": note or "",
            "categorie_filtre": categorie.value if categorie else "",
            "statut_filtre": statut.value if statut else "",
            "total_feedbacks": total,
            "note_moyenne": note_moyenne,
            "repartition": repartition,
            "nb_sans_reponse": nb_sans_reponse,
        },
    )


@router.post("/admin/feedback/{feedback_id}/repondre")
def admin_repondre_feedback(
    request: Request,
    feedback_id: int,
    reponse: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    feedback = session.get(Feedback, feedback_id)
    if not feedback:
        return RedirectResponse("/admin/feedback", status_code=303)

    reponse = reponse.strip()
    if not reponse:
        return RedirectResponse(f"/admin/feedback?erreur=reponse_vide", status_code=303)

    existante = session.exec(
        select(ReponseFeedback).where(ReponseFeedback.feedback_id == feedback_id)
    ).first()
    if existante:
        # Modification d'une reponse deja postee (Partie 6 du brief) —
        # pas de deuxieme ligne creee, ni de deuxieme notification envoyee.
        existante.reponse = reponse
        existante.date_modification = datetime.utcnow()
        session.add(existante)
    else:
        session.add(ReponseFeedback(feedback_id=feedback_id, admin_id=admin.id, reponse=reponse))
        feedback.statut = StatutFeedback.REPONDU
        session.add(feedback)
        _creer_notification_reponse(session, feedback)
    session.commit()

    return RedirectResponse("/admin/feedback?repondu=1", status_code=303)


@router.post("/admin/feedback/{feedback_id}/statut")
def admin_changer_statut_feedback(
    request: Request,
    feedback_id: int,
    statut: StatutFeedback = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    feedback = session.get(Feedback, feedback_id)
    if feedback:
        feedback.statut = statut
        feedback.date_modification = datetime.utcnow()
        session.add(feedback)
        session.commit()
    return RedirectResponse("/admin/feedback?statut_modifie=1", status_code=303)


@router.post("/admin/feedback/{feedback_id}/masquer")
def admin_masquer_feedback(
    request: Request,
    feedback_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Masque un avis publiquement (Partie 6 du brief), sans le supprimer :
    reste consultable/traitable depuis l'admin, mais disparait de la
    section publique '/feedback' meme s'il avait ete marque est_public."""
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    feedback = session.get(Feedback, feedback_id)
    if feedback:
        feedback.statut = StatutFeedback.MASQUE
        feedback.date_modification = datetime.utcnow()
        session.add(feedback)
        session.commit()
    return RedirectResponse("/admin/feedback?masque=1", status_code=303)
