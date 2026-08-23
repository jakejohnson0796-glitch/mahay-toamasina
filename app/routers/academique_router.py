"""
Endpoints JSON en lecture seule pour les selecteurs academiques en
cascade (§7-8 du brief refonte academique nationale) : permettent au
JS du formulaire d'inscription de charger dynamiquement, a chaque
etape, uniquement les options rattachees au choix precedent.

Universite -> Composante (Faculte) -> Filiere/Parcours (avec Mention
et Domaine affiches en lecture seule des que connus). Le Niveau n'a
pas besoin d'endpoint : c'est une liste fixe (app/referentiel.NIVEAUX),
deja rendue directement par le template.

Aucune ecriture ici — la creation/modification du referentiel reste
reservee a /admin/referentiel (voir admin_referentiel_router.py).
"""
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..database import get_session
from ..models import Faculte, Filiere, Mention, Universite

router = APIRouter(prefix="/api/academique")


@router.get("/universites")
def lister_universites(session: Session = Depends(get_session)):
    universites = session.exec(
        select(Universite).where(Universite.est_active == True).order_by(Universite.nom)  # noqa: E712
    ).all()
    return [{"id": u.id, "nom": u.nom, "ville": u.ville} for u in universites]


@router.get("/universites/{universite_id}/composantes")
def lister_composantes(universite_id: int, session: Session = Depends(get_session)):
    composantes = session.exec(
        select(Faculte).where(Faculte.universite_id == universite_id).order_by(Faculte.nom)
    ).all()
    return [{"id": c.id, "nom": c.nom} for c in composantes]


@router.get("/composantes/{composante_id}/filieres")
def lister_filieres(composante_id: int, session: Session = Depends(get_session)):
    """Renvoie aussi mention/domaine (quand connus) pour affichage en
    lecture seule sous le select — l'etudiant VOIT sa mention/domaine
    se remplir automatiquement au choix du parcours, sans jamais les
    saisir lui-meme (§26 : aucune saisie libre)."""
    filieres = session.exec(
        select(Filiere).where(Filiere.faculte_id == composante_id).order_by(Filiere.nom)
    ).all()
    resultat = []
    for f in filieres:
        mention = session.get(Mention, f.mention_id) if f.mention_id else None
        resultat.append({
            "id": f.id,
            "nom": f.nom,
            "mention": mention.nom if mention else None,
            "domaine": (mention.domaine.nom if mention and mention.domaine else None),
        })
    return resultat
