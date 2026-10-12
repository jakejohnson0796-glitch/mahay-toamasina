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
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlmodel import Session, select

from ..database import get_session
from ..models import Domaine, Faculte, Filiere, Mention, Universite, ProgrammeUniversitaire
from ..referentiel import NIVEAUX
from ..texte_normalise import normaliser as _normaliser_nom_parcours

router = APIRouter(prefix="/api/academique")


@router.get("/universites")
def lister_universites(session: Session = Depends(get_session)):
    universites = session.exec(
        select(Universite).where(Universite.est_active == True).order_by(Universite.nom)  # noqa: E712
    ).all()
    return [{"id": u.id, "nom": u.nom, "ville": u.ville} for u in universites]


@router.get("/universites/{universite_id}/cascade")
def charger_cascade_inscription(universite_id: int, session: Session = Depends(get_session)):
    """Charge en une seule requête la hiérarchie nécessaire à l'inscription :
    composante -> mention -> parcours/niveau.

    L'ancien frontend effectuait plusieurs appels réseau successifs. Sur
    Supabase, la latence de chaque aller-retour pouvait rendre les selects
    inactifs plusieurs secondes. Ce endpoint prépare tout le catalogue de
    l'université en un seul aller-retour ; le navigateur filtre ensuite
    instantanément selon la composante, la mention et le niveau choisis.
    """
    universite = session.get(Universite, universite_id)
    if not universite or not universite.est_active:
        return {"composantes": []}

    lignes = session.exec(
        select(Faculte, Filiere, Mention)
        .join(Filiere, Filiere.faculte_id == Faculte.id)
        .join(Mention, Mention.id == Filiere.mention_id)
        .join(ProgrammeUniversitaire, ProgrammeUniversitaire.filiere_id == Filiere.id)
        .where(
            Faculte.universite_id == universite_id,
            Mention.est_active == True,  # noqa: E712
            ProgrammeUniversitaire.universite_id == universite_id,
            ProgrammeUniversitaire.est_active == True,  # noqa: E712
        )
        .order_by(Faculte.nom, Mention.nom, Filiere.nom)
    ).all()

    composantes: dict[int, dict] = {}
    mentions_par_composante: dict[tuple[int, int], dict] = {}

    for faculte, filiere, mention in lignes:
        composante = composantes.setdefault(
            faculte.id,
            {"id": faculte.id, "nom": faculte.nom, "mentions": []},
        )
        cle_mention = (faculte.id, mention.id)
        entree_mention = mentions_par_composante.get(cle_mention)
        if entree_mention is None:
            entree_mention = {
                "id": mention.id,
                "nom": mention.nom,
                "domaine_id": mention.domaine_id,
                "filieres": [],
            }
            mentions_par_composante[cle_mention] = entree_mention
            composante["mentions"].append(entree_mention)

        if _normaliser_nom_parcours(filiere.nom) == "tronc commun":
            continue

        entree_mention["filieres"].append({
            "id": filiere.id,
            "nom": filiere.nom,
            "nom_officiel": filiere.nom,
            "niveau": filiere.niveau,
        })

    return {"composantes": list(composantes.values())}


@router.get("/universites/{universite_id}/composantes")
def lister_composantes(universite_id: int, session: Session = Depends(get_session)):
    universite = session.get(Universite, universite_id)
    if not universite or not universite.est_active:
        return []

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
    composante = session.get(Faculte, composante_id)
    if not composante or not composante.universite_id:
        return []

    universite = session.get(Universite, composante.universite_id)
    if not universite or not universite.est_active:
        return []

    ids_mentions = session.exec(
        select(Filiere.mention_id)
        .join(ProgrammeUniversitaire, ProgrammeUniversitaire.filiere_id == Filiere.id)
        .where(
            Filiere.faculte_id == composante_id,
            Filiere.mention_id.is_not(None),
            ProgrammeUniversitaire.universite_id == composante.universite_id,
            ProgrammeUniversitaire.est_active == True,  # noqa: E712
        )
        .distinct()
    ).all()
    if not ids_mentions:
        return []
    mentions = session.exec(
        select(Mention)
        .where(Mention.id.in_(ids_mentions), Mention.est_active == True)  # noqa: E712
        .order_by(Mention.nom)
    ).all()
    return [{"id": m.id, "nom": m.nom, "domaine_id": m.domaine_id} for m in mentions]


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
    composante = session.get(Faculte, composante_id)
    if not composante or not composante.universite_id:
        return []

    universite = session.get(Universite, composante.universite_id)
    mention = session.get(Mention, mention_id)
    if not universite or not universite.est_active or not mention or not mention.est_active:
        return []

    filieres = session.exec(
        select(Filiere)
        .join(ProgrammeUniversitaire, ProgrammeUniversitaire.filiere_id == Filiere.id)
        .where(
            Filiere.faculte_id == composante_id,
            Filiere.mention_id == mention_id,
            ProgrammeUniversitaire.universite_id == composante.universite_id,
            ProgrammeUniversitaire.est_active == True,  # noqa: E712
            (Filiere.niveau == niveau) | (Filiere.niveau.is_(None)),
        )
        .distinct()
        .order_by(Filiere.nom)
    ).all()
    filieres = [
        f for f in filieres
        if _normaliser_nom_parcours(f.nom) != "tronc commun"
    ]
    resultat = []
    for f in filieres:
        # Libellé court d'aide à la lecture uniquement : l'identité reste
        # l'id Filiere et le nom canonique officiel en base. Cela rend
        # immédiatement visible « Commerce International » dans le cas
        # officiel L3 « Entreprises agro-industrielles et Commerce International »
        # sans créer une seconde filière ni un second cercle.
        nom_affichage = f.nom
        if (
            niveau == "L3"
            and _normaliser_nom_parcours(f.nom) == _normaliser_nom_parcours(
                "Entreprises agro-industrielles et Commerce International"
            )
        ):
            nom_affichage = "Commerce International — Entreprises agro-industrielles"
        resultat.append({"id": f.id, "nom": nom_affichage, "nom_officiel": f.nom})
    return resultat


@router.get("/domaines")
def lister_domaines(session: Session = Depends(get_session)):
    """Domaines actifs du referentiel national, niveau superieur a la mention."""
    domaines = session.exec(
        select(Domaine).where(Domaine.est_active == True).order_by(Domaine.nom)  # noqa: E712
    ).all()
    return [{"id": d.id, "nom": d.nom} for d in domaines]


@router.get("/domaines/{domaine_id}/mentions")
def lister_mentions_par_domaine(domaine_id: int, session: Session = Depends(get_session)):
    """Mentions actives d'un domaine, pour la cascade Domaine -> Mention."""
    mentions = session.exec(
        select(Mention)
        .where(Mention.domaine_id == domaine_id, Mention.est_active == True)  # noqa: E712
        .order_by(Mention.nom)
    ).all()
    return [{"id": m.id, "nom": m.nom, "domaine_id": m.domaine_id} for m in mentions]


@router.get("/mentions")
def lister_toutes_mentions(session: Session = Depends(get_session)):
    """Toutes les mentions (national, aucun filtre par universite) —
    utilise par la recherche et la creation de cercle (voir
    cercles_router.py) : un cercle est national, jamais rattache a une
    seule universite, donc son formulaire ne doit pas non plus l'etre."""
    mentions = session.exec(
        select(Mention).where(Mention.est_active == True).order_by(Mention.nom)  # noqa: E712
    ).all()
    return [{"id": m.id, "nom": m.nom} for m in mentions]


@router.get("/mentions/{mention_id}/parcours-nationaux")
def lister_parcours_nationaux(
    mention_id: int,
    niveau: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """Parcours nationaux actifs, coherents avec la mention et le niveau.

    Les lignes historiques sans niveau restent candidates, mais quand des
    lignes precises existent pour le niveau demande, elles sont prioritaires.
    Une offre doit appartenir a l'universite de sa composante ; une offre
    active d'une autre universite ne doit pas faire apparaitre un parcours
    qui n'y est pas propose.
    """
    mention = session.get(Mention, mention_id)
    if not mention or not mention.est_active:
        return []
    if niveau and niveau not in NIVEAUX:
        return []

    offres_toutes = select(ProgrammeUniversitaire.id).where(
        ProgrammeUniversitaire.filiere_id == Filiere.id
    ).exists()
    offre_locale_active = select(ProgrammeUniversitaire.id).where(
        ProgrammeUniversitaire.filiere_id == Filiere.id,
        ProgrammeUniversitaire.universite_id == Faculte.universite_id,
        ProgrammeUniversitaire.est_active == True,  # noqa: E712
    ).exists()

    requete = (
        select(Filiere)
        .join(Faculte, Faculte.id == Filiere.faculte_id)
        .join(Universite, Universite.id == Faculte.universite_id)
        .join(Mention, Mention.id == Filiere.mention_id)
        .outerjoin(Domaine, Domaine.id == Mention.domaine_id)
        .where(
            Filiere.mention_id == mention_id,
            Mention.est_active == True,  # noqa: E712
            Universite.est_active == True,  # noqa: E712
            or_(Mention.domaine_id.is_(None), Domaine.est_active == True),  # noqa: E712
            or_(~offres_toutes, offre_locale_active),
        )
    )
    if niveau:
        requete = requete.where((Filiere.niveau == niveau) | (Filiere.niveau.is_(None)))

    filieres = session.exec(requete.distinct().order_by(Filiere.nom, Filiere.id)).all()
    filieres = [
        f for f in filieres
        if _normaliser_nom_parcours(f.nom) != "tronc commun"
    ]

    vus: dict[str, dict] = {}
    priorites: dict[str, int] = {}
    for f in filieres:
        cle = _normaliser_nom_parcours(f.nom)
        priorite = 0 if niveau and f.niveau == niveau else 1
        if cle in vus and priorites[cle] <= priorite:
            continue
        vus[cle] = {"id": f.id, "nom": f.nom}
        priorites[cle] = priorite
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
