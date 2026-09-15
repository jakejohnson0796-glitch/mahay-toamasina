"""
Endpoints JSON en lecture seule pour les selecteurs academiques en
cascade (§7-8 du brief refonte academique nationale) : permettent au
JS du formulaire d'inscription de charger dynamiquement, a chaque
etape, uniquement les options rattachees au choix precedent.

Universite -> Composante (Faculte) -> Mention -> Niveau -> Parcours/
Filiere (facultatif : voir /mentions/{id}/filieres, qui peut renvoyer
une liste vide -- tronc commun, voir le rapport du 10/09/2026 sur
Filiere.niveau). Le Niveau n'a pas besoin d'endpoint : c'est une liste
fixe (app/referentiel.NIVEAUX), deja rendue directement par le
template, et valide a N'IMPORTE QUEL niveau (le tronc commun peut
exister a n'importe quel niveau selon la mention, jamais suppose L1/L2
en dur).

Aucune ecriture ici — la creation/modification du referentiel reste
reservee a /admin/referentiel (voir admin_referentiel_router.py).
"""
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..database import get_session
from ..models import Faculte, Filiere, Mention, Universite
from ..texte_normalise import normaliser as _normaliser_nom_parcours

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


@router.get("/composantes/{composante_id}/mentions")
def lister_mentions(composante_id: int, session: Session = Depends(get_session)):
    """Mentions offertes par cette composante, deduites des Filiere qui
    y sont deja rattachees (une Mention sans AUCUNE Filiere nulle part
    dans cette composante n'a pour l'instant aucun moyen d'etre reliee
    a elle -- limite connue, voir le rapport du 10/09/2026 : concerne
    quelques mentions ENS pour lesquelles seul le tronc commun est
    verifie a ce jour, sans parcours de specialisation encore confirme
    qui permettrait de les rattacher ici automatiquement)."""
    ids_mentions = session.exec(
        select(Filiere.mention_id)
        .where(Filiere.faculte_id == composante_id, Filiere.mention_id.is_not(None))
        .distinct()
    ).all()
    if not ids_mentions:
        return []
    mentions = session.exec(
        select(Mention).where(Mention.id.in_(ids_mentions)).order_by(Mention.nom)
    ).all()
    return [{"id": m.id, "nom": m.nom} for m in mentions]


@router.get("/composantes/{composante_id}/mentions/{mention_id}/filieres")
def lister_filieres_par_mention_niveau(
    composante_id: int, mention_id: int, niveau: str, session: Session = Depends(get_session),
):
    """Parcours nommes pour cette mention, A CE NIVEAU precis, dans
    cette composante. Liste VIDE = tronc commun a ce niveau pour cette
    mention (aucun parcours a choisir, voir le rapport du 10/09/2026) --
    ce n'est pas une erreur, c'est un etat normal et attendu.

    Inclut aussi les Filiere heritees (niveau NULL, pas encore
    enrichies) : moins precises, mais toujours des choix valides."""
    filieres = session.exec(
        select(Filiere).where(
            Filiere.faculte_id == composante_id,
            Filiere.mention_id == mention_id,
            (Filiere.niveau == niveau) | (Filiere.niveau.is_(None)),
        ).order_by(Filiere.nom)
    ).all()
    return [{"id": f.id, "nom": f.nom} for f in filieres]


@router.get("/mentions")
def lister_toutes_mentions(session: Session = Depends(get_session)):
    """Toutes les mentions (national, aucun filtre par universite) —
    utilise par la recherche et la creation de cercle (voir
    cercles_router.py) : un cercle est national, jamais rattache a une
    seule universite, donc son formulaire ne doit pas non plus l'etre."""
    mentions = session.exec(select(Mention).order_by(Mention.nom)).all()
    return [{"id": m.id, "nom": m.nom} for m in mentions]


@router.get("/mentions/{mention_id}/parcours-nationaux")
def lister_parcours_nationaux(mention_id: int, niveau: str, session: Session = Depends(get_session)):
    """Parcours nommes pour cette mention a ce niveau, DEDUPLIQUES par
    nom normalise A TRAVERS TOUTES LES UNIVERSITES (voir
    referentiel_academique._normaliser_nom_parcours) : contrairement a
    /composantes/{id}/mentions/{id}/filieres (scope a une seule
    universite, pour l'inscription), un cercle est national -- "Finance"
    a Toamasina et a Fianarantsoa doit apparaitre comme UNE SEULE
    option, pas deux. Un seul id representant est renvoye par groupe
    (peu importe lequel : voir _filieres_equivalentes, utilisee cote
    recherche/creation de cercle pour retrouver tout le groupe a partir
    de ce representant).

    Liste VIDE = tronc commun a ce niveau pour cette mention (aucun
    parcours a choisir), meme convention que pour l'inscription."""
    filieres = session.exec(
        select(Filiere).where(Filiere.mention_id == mention_id, Filiere.niveau == niveau)
    ).all()

    vus: dict[str, dict] = {}
    for f in filieres:
        cle = _normaliser_nom_parcours(f.nom)
        if cle not in vus:
            vus[cle] = {"id": f.id, "nom": f.nom}
    return sorted(vus.values(), key=lambda p: p["nom"])
def lister_filieres(composante_id: int, session: Session = Depends(get_session)):
    """Renvoie aussi mention/domaine (quand connus) pour affichage en
    lecture seule sous le select — l'etudiant VOIT sa mention/domaine
    se remplir automatiquement au choix du parcours, sans jamais les
    saisir lui-meme (§26 : aucune saisie libre).

    Conserve tel quel (non filtre par mention/niveau) pour les usages
    qui listent encore tous les parcours d'une composante d'un coup —
    voir /admin/referentiel. Le formulaire d'inscription/profil
    academique utilise desormais /mentions et /mentions/{id}/filieres
    ci-dessus, plus precis."""
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
