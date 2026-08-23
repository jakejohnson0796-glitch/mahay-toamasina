"""
Provisionnement automatique des cercles nationaux : un cercle par
combinaison (mention, PARCOURS NATIONAL, niveau), pour chaque parcours
deja rattache a une mention.

Contrairement au workflow de demande manuelle (DemandeCreationCercle,
toujours soumis a validation admin — la ou un etudiant demande un
cercle pour une combinaison qui n'existe pas encore et doit justifier
pourquoi), ce provisionnement-ci est purement mecanique : la mention
et la filiere sont deja connues avec certitude (assignation explicite
d'un admin via /admin/referentiel, jamais devinee — voir §44 du brief
refonte academique), seul le produit cartesien avec les 8 niveaux
restait a generer. Aucune ambiguite ici, donc pas besoin d'un circuit
d'approbation pour cette etape precise.

IMPORTANT — identite d'un "parcours national" (corrige suite a un bug
de doublons signale par Jake apres l'import du referentiel MESUPRES) :
la table Filiere est scopee par universite (Filiere.faculte_id ->
Faculte.universite_id), donc CHAQUE universite qui offre le meme
parcours (ex: "Finance") a sa PROPRE ligne Filiere, avec un id
different. Un cercle national ne doit PAS etre identifie par
filiere_id brut (§16-18 du brief : "Ne pas creer un cercle different
pour chaque universite") — il est identifie par (mention_id, NOM DE
PARCOURS NORMALISE, niveau). Toutes les Filiere qui partagent la meme
mention et le meme nom normalise (independamment de l'universite) sont
donc regroupees en UN SEUL cercle, qui reference arbitrairement l'une
d'entre elles (la premiere par id) — la recherche/appartenance ne
depend de toute facon que de mention_id+niveau au niveau du cercle,
jamais de savoir laquelle des Filiere equivalentes a ete choisie comme
representante.

Filieres SANS mention assignee : volontairement ignorees (voir
nb_filieres_sans_mention sur /admin/referentiel) tant qu'un admin n'a
pas confirme la mention — sinon l'identite du cercle national serait
incomplete/ambigue, exactement ce que §44 interdit.

Idempotent : peut tourner a chaque demarrage (main.py, apres
assurer_compte_admin) et a chaque assignation de mention
(admin_referentiel_router.assigner_mention_filiere) sans jamais
recreer un cercle deja existant — y compris un cercle deja cree pour
une AUTRE Filiere du meme groupe (meme mention + meme nom normalise).
"""
import logging
from typing import Optional

from sqlmodel import Session, select

from .models import (
    CercleEtude, Filiere, MembreCercle, RoleMembreCercle, RoleUtilisateur,
    StatutCercle, Utilisateur,
)
from .referentiel import NIVEAUX, libelle_niveau
from .texte_normalise import normaliser as _normaliser_nom_parcours

logger = logging.getLogger("mahay.cercles_referentiel")


def _createur_systeme(session: Session) -> Optional[Utilisateur]:
    """Premier compte admin trouve : sert de createur_id pour les
    cercles generes automatiquement (CercleEtude.createur_id n'est pas
    nullable). None si aucun admin n'existe encore au moment de
    l'appel — l'appelant reporte alors simplement le provisionnement."""
    return session.exec(
        select(Utilisateur).where(Utilisateur.role == RoleUtilisateur.ADMIN)
    ).first()


def assurer_cercles_pour_groupe_parcours(
    session: Session, mention_id: int, filieres_du_groupe: list[Filiere], createur: Utilisateur
) -> int:
    """Cree, pour un GROUPE de Filiere representant le meme parcours
    national (meme mention_id + meme nom normalise, potentiellement
    plusieurs universites), le cercle manquant pour chaque niveau —
    UN SEUL cercle par niveau pour tout le groupe, jamais un par
    Filiere. Renvoie le nombre de cercles effectivement crees."""
    from .routers.cercles_router import _assurer_membres_admins

    filiere_ids_du_groupe = [f.id for f in filieres_du_groupe]
    # Representante arbitraire (la plus ancienne = id le plus petit) :
    # le cercle doit bien referencer UNE Filiere pour sa FK, mais
    # laquelle n'a pas d'importance — voir la docstring du module.
    filiere_representante = min(filieres_du_groupe, key=lambda f: f.id)

    niveaux_existants = {
        c.niveau
        for c in session.exec(
            select(CercleEtude).where(
                CercleEtude.mention_id == mention_id,
                CercleEtude.filiere_id.in_(filiere_ids_du_groupe),
                CercleEtude.statut == StatutCercle.ACTIF,
            )
        ).all()
    }

    nb_crees = 0
    for niveau in NIVEAUX:
        if niveau in niveaux_existants:
            continue

        cercle = CercleEtude(
            nom=f"{filiere_representante.nom} — {libelle_niveau(niveau)}",
            mention_id=mention_id,
            filiere_id=filiere_representante.id,
            niveau=niveau,
            statut=StatutCercle.ACTIF,
            createur_id=createur.id,
        )
        session.add(cercle)
        session.commit()
        session.refresh(cercle)

        session.add(MembreCercle(
            cercle_id=cercle.id, utilisateur_id=createur.id, role=RoleMembreCercle.CREATEUR,
        ))
        session.commit()

        # Hierarchie ADMIN_GLOBAL > OWNER (voir cercles_router.py) : tout
        # admin doit avoir acces immediat, meme aux cercles generes
        # automatiquement, sans avoir a le rejoindre.
        _assurer_membres_admins(session, cercle.id)

        nb_crees += 1

    return nb_crees


def assurer_cercles_pour_filiere(session: Session, filiere: Filiere, createur: Utilisateur) -> int:
    """Point d'entree conserve pour admin_referentiel_router.py (appele
    juste apres qu'un admin vient d'assigner/changer la mention d'UNE
    filiere precise, pour provisionner ses cercles sans attendre le
    prochain redemarrage). Retrouve le GROUPE complet de cette filiere
    (meme mention + meme nom normalise, potentiellement d'autres
    universites) avant de deleguer a assurer_cercles_pour_groupe_parcours
    — sinon un admin qui rattache la 2e universite d'un parcours deja
    provisionne ailleurs recreerait exactement le doublon que ce module
    corrige (voir sa docstring)."""
    if not filiere.mention_id:
        return 0

    nom_normalise = _normaliser_nom_parcours(filiere.nom)
    filieres_du_groupe = [
        f for f in session.exec(select(Filiere).where(Filiere.mention_id == filiere.mention_id)).all()
        if _normaliser_nom_parcours(f.nom) == nom_normalise
    ]
    return assurer_cercles_pour_groupe_parcours(session, filiere.mention_id, filieres_du_groupe, createur)


def assurer_cercles_referentiel(session: Session) -> int:
    """Parcourt TOUTES les filieres deja rattachees a une mention,
    les regroupe par parcours national (mention_id + nom normalise —
    voir la docstring du module), et garantit qu'UN SEUL cercle existe
    par groupe et par niveau. Appelee au demarrage (main.py, apres
    assurer_compte_admin) et peut etre appelee a nouveau sans risque
    (idempotente). Renvoie le nombre total de cercles crees (0 si tout
    existait deja)."""
    createur = _createur_systeme(session)
    if not createur:
        logger.warning(
            "Aucun compte admin trouve : provisionnement automatique des "
            "cercles nationaux reporte (createur_id requis)."
        )
        return 0

    filieres = session.exec(
        select(Filiere).where(Filiere.mention_id.is_not(None))
    ).all()

    groupes: dict[tuple[int, str], list[Filiere]] = {}
    for filiere in filieres:
        cle = (filiere.mention_id, _normaliser_nom_parcours(filiere.nom))
        groupes.setdefault(cle, []).append(filiere)

    total = 0
    for (mention_id, _nom_normalise), filieres_du_groupe in groupes.items():
        total += assurer_cercles_pour_groupe_parcours(session, mention_id, filieres_du_groupe, createur)

    if total:
        logger.info("%d cercle(s) national/nationaux provisionne(s) automatiquement.", total)

    return total
