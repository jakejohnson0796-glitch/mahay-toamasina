"""
FAQ publique (/faq) et gestion admin de la FAQ (/admin/faq).

Suit le meme style que documents_router.py / admin_router.py : garde-fou
admin local (pas de dependance FastAPI globale, coherent avec le reste du
projet), CSRF sur chaque route qui modifie l'etat, recherche cote serveur
via un parametre `q` (meme pattern que page_utilisateurs() dans
admin_router.py).
"""
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..auth import utilisateur_courant
from ..models import FAQ, CategorieFAQ, Utilisateur, RoleUtilisateur

router = APIRouter()


def _admin_requis(request: Request, session: Session) -> Optional[Utilisateur]:
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return None
    return utilisateur


# ============================================================
# FAQ publique
# ============================================================

@router.get("/faq")
def page_faq(
    request: Request,
    q: Optional[str] = None,
    categorie: Optional[CategorieFAQ] = None,
    session: Session = Depends(get_session),
):
    requete = select(FAQ).where(FAQ.est_active == True)  # noqa: E712
    if categorie:
        requete = requete.where(FAQ.categorie == categorie)
    if q:
        # Recherche insensible a la casse dans la question ET la reponse
        # (Partie 1 du brief). SQLite/Postgres traitent tous deux LIKE/ILIKE
        # avec une casse deja insensible sur les colonnes texte usuelles,
        # mais on force explicitement via ilike() pour un comportement
        # identique sur les deux moteurs (voir database.py).
        motif = f"%{q.strip()}%"
        requete = requete.where(
            (FAQ.question.ilike(motif)) | (FAQ.reponse.ilike(motif))
        )
    questions = session.exec(requete.order_by(FAQ.ordre_affichage, FAQ.id)).all()

    return templates.TemplateResponse(
        request,
        "faq.html",
        {
            "utilisateur": utilisateur_courant(request, session),
            "questions": questions,
            "categories": list(CategorieFAQ),
            "q": q or "",
            "categorie_filtre": categorie.value if categorie else "",
        },
    )


# ============================================================
# Administration de la FAQ
# ============================================================

@router.get("/admin/faq")
def admin_liste_faq(
    request: Request,
    q: Optional[str] = None,
    categorie: Optional[CategorieFAQ] = None,
    statut: Optional[str] = None,  # "actives" | "inactives" | None (toutes)
    session: Session = Depends(get_session),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    requete = select(FAQ)
    if categorie:
        requete = requete.where(FAQ.categorie == categorie)
    if statut == "actives":
        requete = requete.where(FAQ.est_active == True)  # noqa: E712
    elif statut == "inactives":
        requete = requete.where(FAQ.est_active == False)  # noqa: E712
    if q:
        motif = f"%{q.strip()}%"
        requete = requete.where(
            (FAQ.question.ilike(motif)) | (FAQ.reponse.ilike(motif))
        )
    questions = session.exec(requete.order_by(FAQ.ordre_affichage, FAQ.id)).all()

    return templates.TemplateResponse(
        request,
        "admin_faq.html",
        {
            "utilisateur": admin,
            "questions": questions,
            "categories": list(CategorieFAQ),
            "q": q or "",
            "categorie_filtre": categorie.value if categorie else "",
            "statut_filtre": statut or "",
        },
    )


@router.post("/admin/faq")
def admin_creer_faq(
    request: Request,
    question: str = Form(...),
    reponse: str = Form(...),
    categorie: CategorieFAQ = Form(...),
    ordre_affichage: int = Form(0),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    question = question.strip()
    reponse = reponse.strip()
    if not question or not reponse:
        return RedirectResponse("/admin/faq?erreur=champs_requis", status_code=303)

    faq = FAQ(
        question=question,
        reponse=reponse,
        categorie=categorie,
        ordre_affichage=ordre_affichage,
        cree_par_id=admin.id,
    )
    session.add(faq)
    session.commit()
    return RedirectResponse("/admin/faq?cree=1", status_code=303)


@router.post("/admin/faq/{faq_id}/modifier")
def admin_modifier_faq(
    request: Request,
    faq_id: int,
    question: str = Form(...),
    reponse: str = Form(...),
    categorie: CategorieFAQ = Form(...),
    ordre_affichage: int = Form(0),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    from datetime import datetime

    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    faq = session.get(FAQ, faq_id)
    if not faq:
        return RedirectResponse("/admin/faq", status_code=303)

    question = question.strip()
    reponse = reponse.strip()
    if not question or not reponse:
        return RedirectResponse("/admin/faq?erreur=champs_requis", status_code=303)

    faq.question = question
    faq.reponse = reponse
    faq.categorie = categorie
    faq.ordre_affichage = ordre_affichage
    faq.date_modification = datetime.utcnow()
    session.add(faq)
    session.commit()
    return RedirectResponse("/admin/faq?modifie=1", status_code=303)


@router.post("/admin/faq/{faq_id}/basculer-actif")
def admin_basculer_actif_faq(
    request: Request,
    faq_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    faq = session.get(FAQ, faq_id)
    if faq:
        faq.est_active = not faq.est_active
        session.add(faq)
        session.commit()
    return RedirectResponse("/admin/faq", status_code=303)


@router.post("/admin/faq/{faq_id}/supprimer")
def admin_supprimer_faq(
    request: Request,
    faq_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Suppression LOGIQUE (est_active = False), pas physique — coherent
    avec la Partie 2 du brief ('si possible, suppression logique plutot
    que physique') et avec le pattern deja utilise (Universite.est_active,
    Mention.est_active). Le bouton "Supprimer" cote admin desactive donc
    la question ; elle reste filtrable via statut=inactives et peut etre
    reactivee sans perte de contenu."""
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    faq = session.get(FAQ, faq_id)
    if faq:
        faq.est_active = False
        session.add(faq)
        session.commit()
    return RedirectResponse("/admin/faq?supprime=1", status_code=303)
