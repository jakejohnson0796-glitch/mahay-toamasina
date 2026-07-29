"""
Espace 'sponsor' : repetiteurs, petits commerces ou services autour du
campus qui paient un abonnement mensuel pour etre mis en avant aupres des
etudiants. C'est ce cote du marche qui finance la plateforme, PAS
l'etudiant — voir la note sur le modele economique dans le README.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from ..database import get_session
from ..models import Abonnement, StatutAbonnement
from ..auth import utilisateur_courant

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# A ajuster apres des tests reels de "combien un repetiteur/sponsor est
# pret a payer par mois pour toucher les etudiants de l'universite".
PRIX_ABONNEMENT_ARIARY = 15000


@router.get("/sponsoring")
def page_sponsoring(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(
        request,
        "sponsoring.html",
        {
            "utilisateur": utilisateur_courant(request, session),
            "prix": PRIX_ABONNEMENT_ARIARY,
        },
    )


@router.post("/sponsoring/souscrire")
def souscrire(
    request: Request,
    fournisseur_paiement: str = Form(...),
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    # TODO (V2) : remplacer ce bloc par un vrai appel a une passerelle mobile
    # money malgache (PayBriq, Efaina ou Voaray gerent MVola/Orange Money/
    # Airtel Money derriere une seule API). Ne creer l'abonnement en statut
    # ACTIF qu'apres confirmation du paiement via leur webhook, jamais avant.
    abonnement = Abonnement(
        utilisateur_id=utilisateur.id,
        prix_ariary=PRIX_ABONNEMENT_ARIARY,
        fournisseur_paiement=fournisseur_paiement,
        statut=StatutAbonnement.EN_ATTENTE_PAIEMENT,
        date_debut=datetime.utcnow(),
        date_fin=datetime.utcnow() + timedelta(days=30),
    )
    session.add(abonnement)
    session.commit()
    return RedirectResponse("/sponsoring?demande_envoyee=1", status_code=303)
