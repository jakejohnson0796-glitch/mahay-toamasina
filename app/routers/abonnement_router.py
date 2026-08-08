"""
Abonnement Premium etudiant : statut/essai cote etudiant, plus les
actions admin de validation. Distinct de sponsoring_router.py qui gere
un tout autre public (sponsors/repetiteurs) avec une autre logique
d'activation (automatique, pas de validation manuelle).
"""
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..models import RoleUtilisateur, StatutAbonnementEtudiant, AbonnementEtudiant, Utilisateur
from ..auth import utilisateur_courant
from ..storage import sauvegarder_fichier, obtenir_url_telechargement, stockage_distant_actif
from .. import subscription

router = APIRouter()


# ---------------------------------------------------------------------
# Cote etudiant
# ---------------------------------------------------------------------

@router.get("/abonnement")
def page_abonnement(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    abonnement = subscription.obtenir_abonnement(session, utilisateur.id)
    if abonnement:
        abonnement = subscription.synchroniser_expiration(session, abonnement)

    return templates.TemplateResponse(
        request,
        "abonnement.html",
        {
            "utilisateur": utilisateur,
            "abonnement": abonnement,
            "acces_premium": subscription.acces_premium_valide(abonnement),
            "jours_restants": subscription.jours_restants(abonnement),
            "prix": subscription.PRIX_ABONNEMENT_ETUDIANT_ARIARY,
            "StatutAbonnementEtudiant": StatutAbonnementEtudiant,
        },
    )


@router.post("/abonnement/demande")
def soumettre_demande(
    request: Request,
    fournisseur_paiement: str = Form(...),
    reference_paiement: Optional[str] = Form(None),
    preuve: Optional[UploadFile] = File(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    abonnement = subscription.obtenir_abonnement(session, utilisateur.id)
    if not abonnement:
        # Ne devrait pas arriver (essai cree a l'inscription), garde-fou
        # defensif pour ne pas planter si des comptes plus anciens
        # existaient avant cette fonctionnalite.
        abonnement = subscription.creer_essai_gratuit(session, utilisateur)

    chemin_preuve = None
    if preuve is not None and preuve.filename:
        reference = f"preuve_abonnement_{utilisateur.id}_{abonnement.id}"
        chemin_preuve = sauvegarder_fichier(preuve, reference)

    subscription.soumettre_demande_abonnement(
        session,
        abonnement,
        fournisseur_paiement=fournisseur_paiement,
        reference_paiement=reference_paiement or None,
        preuve_paiement_chemin=chemin_preuve,
    )
    return RedirectResponse("/abonnement?demande_envoyee=1", status_code=303)


# ---------------------------------------------------------------------
# Cote admin
# ---------------------------------------------------------------------

def _admin_requis(request: Request, session: Session):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return None
    return utilisateur


@router.get("/admin/abonnements")
def admin_liste_abonnements(
    request: Request,
    statut: Optional[StatutAbonnementEtudiant] = None,
    session: Session = Depends(get_session),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    requete = select(AbonnementEtudiant, Utilisateur).join(
        Utilisateur, AbonnementEtudiant.utilisateur_id == Utilisateur.id
    )
    if statut:
        requete = requete.where(AbonnementEtudiant.statut == statut)
    else:
        # Par defaut : ce qui demande vraiment une action de l'admin.
        requete = requete.where(AbonnementEtudiant.statut == StatutAbonnementEtudiant.EN_ATTENTE)

    resultats = session.exec(requete.order_by(AbonnementEtudiant.date_maj.desc())).all()

    return templates.TemplateResponse(
        request,
        "admin_abonnements.html",
        {
            "utilisateur": admin,
            "lignes": resultats,
            "statut_filtre": statut,
            "StatutAbonnementEtudiant": StatutAbonnementEtudiant,
        },
    )


@router.post("/admin/abonnements/{abonnement_id}/valider")
def admin_valider(request: Request, abonnement_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    abonnement = session.get(AbonnementEtudiant, abonnement_id)
    if abonnement:
        subscription.valider_abonnement(session, abonnement, admin_id=admin.id)
    return RedirectResponse("/admin/abonnements", status_code=303)


@router.post("/admin/abonnements/{abonnement_id}/refuser")
def admin_refuser(
    request: Request,
    abonnement_id: int,
    motif: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    abonnement = session.get(AbonnementEtudiant, abonnement_id)
    if abonnement:
        subscription.refuser_abonnement(session, abonnement, admin_id=admin.id, motif=motif)
    return RedirectResponse("/admin/abonnements", status_code=303)


@router.post("/admin/abonnements/{abonnement_id}/prolonger")
def admin_prolonger(
    request: Request,
    abonnement_id: int,
    jours: int = Form(subscription.DUREE_PROLONGATION_JOURS),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    abonnement = session.get(AbonnementEtudiant, abonnement_id)
    if abonnement:
        subscription.prolonger_abonnement(session, abonnement, admin_id=admin.id, jours=jours)
    return RedirectResponse("/admin/abonnements", status_code=303)


@router.get("/admin/abonnements/{abonnement_id}/preuve")
def admin_voir_preuve(request: Request, abonnement_id: int, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    abonnement = session.get(AbonnementEtudiant, abonnement_id)
    if not abonnement or not abonnement.preuve_paiement_chemin:
        return RedirectResponse("/admin/abonnements", status_code=303)

    if stockage_distant_actif():
        return RedirectResponse(obtenir_url_telechargement(abonnement.preuve_paiement_chemin))
    return FileResponse(abonnement.preuve_paiement_chemin)
