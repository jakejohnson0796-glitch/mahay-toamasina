"""
Espace 'sponsor' : repetiteurs, petits commerces ou services autour du
campus qui paient pour etre mis en avant aupres des etudiants. C'est ce
cote du marche qui finance la plateforme, PAS l'etudiant — voir la note
sur le modele economique dans le README.

Pas de prix fixe affiche sur cette page : chaque sponsor est different
(repetiteur individuel, petit commerce, service...), donc le tarif est
negocie au cas par cas APRES ce premier contact, pas impose a l'avance.
La route publique /sponsoring/contact ne fait qu'enregistrer la demande ;
c'est un admin qui, une fois le prix convenu hors-ligne avec le sponsor,
la fait passer a ACTIF via /admin/sponsors en renseignant a ce moment-la
le prix et le moyen de paiement retenus (voir plus bas, cote admin).
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..models import Abonnement, StatutAbonnement, RoleUtilisateur, Utilisateur
from ..auth import utilisateur_courant

router = APIRouter()

LONGUEUR_MAX_MESSAGE = 2000
DUREE_PARTENARIAT_JOURS = 30


@router.get("/sponsoring")
def page_sponsoring(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(
        request,
        "sponsoring.html",
        {
            "utilisateur": utilisateur_courant(request, session),
        },
    )


@router.post("/sponsoring/contact")
def demander_contact(
    request: Request,
    message: str = Form(""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Enregistre une demande de contact sponsor. Aucun prix ni moyen de
    paiement n'est demande ici : les deux seront discutes directement
    avec le sponsor, puis renseignes par un admin au moment de valider
    le partenariat (voir StatutAbonnement.ACTIF)."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    abonnement = Abonnement(
        utilisateur_id=utilisateur.id,
        message=(message or "").strip()[:LONGUEUR_MAX_MESSAGE] or None,
        statut=StatutAbonnement.EN_ATTENTE_PAIEMENT,
        date_debut=datetime.utcnow(),
    )
    session.add(abonnement)
    session.commit()
    return RedirectResponse("/sponsoring?demande_envoyee=1", status_code=303)


# ---------------------------------------------------------------------
# Cote admin : traitement des demandes de contact sponsor
# ---------------------------------------------------------------------

def _admin_requis(request: Request, session: Session) -> Optional[Utilisateur]:
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return None
    return utilisateur


@router.get("/admin/sponsors")
def admin_liste_sponsors(
    request: Request,
    statut: Optional[StatutAbonnement] = None,
    session: Session = Depends(get_session),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    requete = select(Abonnement, Utilisateur).join(Utilisateur, Abonnement.utilisateur_id == Utilisateur.id)
    if statut:
        requete = requete.where(Abonnement.statut == statut)
    else:
        # Par defaut : les demandes de contact pas encore traitees, ce
        # qui demande vraiment une action de l'admin en priorite.
        requete = requete.where(Abonnement.statut == StatutAbonnement.EN_ATTENTE_PAIEMENT)

    resultats = session.exec(requete.order_by(Abonnement.date_debut.desc())).all()

    return templates.TemplateResponse(
        request,
        "admin_sponsors.html",
        {
            "utilisateur": admin,
            "lignes": resultats,
            "statut_filtre": statut,
            "StatutAbonnement": StatutAbonnement,
        },
    )


@router.post("/admin/sponsors/{abonnement_id}/valider")
def admin_valider_sponsor(
    request: Request,
    abonnement_id: int,
    prix_ariary: int = Form(...),
    fournisseur_paiement: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Active le partenariat une fois le prix negocie hors-ligne avec le
    sponsor : c'est ICI, et uniquement ici, que prix_ariary et
    fournisseur_paiement sont renseignes — jamais choisis par le sponsor
    lui-meme sur le site (voir la note en tete de fichier)."""
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    abonnement = session.get(Abonnement, abonnement_id)
    if abonnement:
        maintenant = datetime.utcnow()
        abonnement.prix_ariary = prix_ariary
        abonnement.fournisseur_paiement = fournisseur_paiement
        abonnement.statut = StatutAbonnement.ACTIF
        abonnement.date_debut = maintenant
        abonnement.date_fin = maintenant + timedelta(days=DUREE_PARTENARIAT_JOURS)
        session.add(abonnement)
        session.commit()
    return RedirectResponse("/admin/sponsors", status_code=303)


@router.post("/admin/sponsors/{abonnement_id}/refuser")
def admin_refuser_sponsor(
    request: Request,
    abonnement_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Cloture une demande sans y donner suite (pas d'accord trouve,
    hors cible...). Reutilise le statut EXPIRE : pas de statut REFUSE
    dedie, pour eviter une migration ALTER TYPE sur l'enum Postgres
    native cote Supabase — le sens ('pas/plus de partenariat actif')
    est le meme que pour un partenariat expire."""
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    abonnement = session.get(Abonnement, abonnement_id)
    if abonnement:
        abonnement.statut = StatutAbonnement.EXPIRE
        session.add(abonnement)
        session.commit()
    return RedirectResponse("/admin/sponsors", status_code=303)
