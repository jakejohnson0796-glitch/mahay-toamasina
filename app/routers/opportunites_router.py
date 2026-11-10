"""Catalogue d'opportunités académiques, avec publication contrôlée par l'administration."""
from datetime import date, datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..auth import utilisateur_courant
from ..csrf import verifier_csrf
from ..database import get_session
from ..models import OpportuniteAcademique, RoleUtilisateur
from ..templating import templates

router = APIRouter()
CATEGORIES = ("bourse", "concours", "admission", "stage", "formation", "evenement")


def _admin(request: Request, session: Session):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return None
    return utilisateur


def _source_http_valide(url: str) -> bool:
    try:
        parsed = urlsplit((url or "").strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname)
    except ValueError:
        return False


@router.get("/opportunites")
def page_opportunites(
    request: Request,
    categorie: str | None = None,
    niveau: str | None = None,
    session: Session = Depends(get_session),
):
    aujourd_hui = date.today()
    requete = select(OpportuniteAcademique).where(
        OpportuniteAcademique.statut == "publiee"
    ).where(
        (OpportuniteAcademique.date_limite.is_(None))
        | (OpportuniteAcademique.date_limite >= aujourd_hui)
    ).order_by(OpportuniteAcademique.date_limite.asc(), OpportuniteAcademique.date_creation.desc())
    if categorie in CATEGORIES:
        requete = requete.where(OpportuniteAcademique.categorie == categorie)
    if niveau and len(niveau) <= 80:
        requete = requete.where(OpportuniteAcademique.niveau_cible == niveau)
    offres = session.exec(requete.limit(100)).all()
    return templates.TemplateResponse(
        request,
        "opportunites.html",
        {
            "utilisateur": utilisateur_courant(request, session),
            "opportunites": offres,
            "categorie_active": categorie if categorie in CATEGORIES else "",
            "niveau_actif": niveau or "",
            "categories": CATEGORIES,
            "aujourd_hui": aujourd_hui,
        },
    )


@router.get("/admin/opportunites")
def admin_opportunites(request: Request, session: Session = Depends(get_session)):
    admin = _admin(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    offres = session.exec(
        select(OpportuniteAcademique).order_by(OpportuniteAcademique.date_creation.desc()).limit(200)
    ).all()
    return templates.TemplateResponse(
        request,
        "admin_opportunites.html",
        {"utilisateur": admin, "opportunites": offres, "categories": CATEGORIES,
         "erreur": request.query_params.get("erreur"), "ok": request.query_params.get("ok")},
    )


@router.post("/admin/opportunites/creer")
def creer_opportunite(
    request: Request,
    titre: str = Form(...),
    categorie: str = Form(...),
    description: str = Form(...),
    source_nom: str = Form(...),
    source_url: str = Form(...),
    niveau_cible: str = Form(""),
    region: str = Form(""),
    date_limite: str = Form(""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    titre, description = titre.strip(), description.strip()
    source_nom, source_url = source_nom.strip(), source_url.strip()
    if not titre or len(titre) > 180 or not description or len(description) > 5000:
        return RedirectResponse("/admin/opportunites?erreur=champs", status_code=303)
    if categorie not in CATEGORIES or not source_nom or len(source_nom) > 180 or not _source_http_valide(source_url):
        return RedirectResponse("/admin/opportunites?erreur=source", status_code=303)
    limite = None
    if date_limite.strip():
        try:
            limite = date.fromisoformat(date_limite.strip())
        except ValueError:
            return RedirectResponse("/admin/opportunites?erreur=date", status_code=303)
    offre = OpportuniteAcademique(
        titre=titre,
        categorie=categorie,
        description=description,
        niveau_cible=niveau_cible.strip()[:80] or None,
        region=region.strip()[:100] or None,
        date_limite=limite,
        source_nom=source_nom,
        source_url=source_url,
        statut="brouillon",
        cree_par_id=admin.id,
    )
    session.add(offre)
    session.commit()
    return RedirectResponse("/admin/opportunites?ok=cree", status_code=303)


@router.post("/admin/opportunites/{opportunite_id}/publier")
def publier_opportunite(
    opportunite_id: int,
    request: Request,
    source_verifiee: str = Form(""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    offre = session.get(OpportuniteAcademique, opportunite_id)
    if not offre:
        return RedirectResponse("/admin/opportunites?erreur=introuvable", status_code=303)
    if source_verifiee != "oui" or not _source_http_valide(offre.source_url):
        return RedirectResponse("/admin/opportunites?erreur=verification", status_code=303)
    offre.statut = "publiee"
    offre.verifiee_le = datetime.utcnow()
    offre.verifiee_par_id = admin.id
    offre.date_modification = datetime.utcnow()
    session.add(offre)
    session.commit()
    return RedirectResponse("/admin/opportunites?ok=publiee", status_code=303)


@router.post("/admin/opportunites/{opportunite_id}/archiver")
def archiver_opportunite(
    opportunite_id: int,
    request: Request,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    offre = session.get(OpportuniteAcademique, opportunite_id)
    if offre:
        offre.statut = "archivee"
        offre.date_modification = datetime.utcnow()
        session.add(offre)
        session.commit()
    return RedirectResponse("/admin/opportunites?ok=archivee", status_code=303)
