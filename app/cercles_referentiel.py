"""
Provisionnement automatique des cercles nationaux : un cercle par
combinaison (mention, filiere, niveau), pour chaque Filiere deja
rattachee a une Mention.

Contrairement au workflow de demande manuelle (DemandeCreationCercle,
toujours soumis a validation admin — la ou un etudiant demande un
cercle pour une combinaison qui n'existe pas encore et doit justifier
pourquoi), ce provisionnement-ci est purement mecanique : la mention
et la filiere sont deja connues avec certitude (assignation explicite
d'un admin via /admin/referentiel, jamais devinee — voir §44 du brief
refonte academique), seul le produit cartesien avec les 8 niveaux
restait a generer. Aucune ambiguite ici, donc pas besoin d'un circuit
d'approbation pour cette etape precise.

Filieres SANS mention assignee : volontairement ignorees (voir
nb_filieres_sans_mention sur /admin/referentiel) tant qu'un admin n'a
pas confirme la mention — sinon l'identite du cercle national serait
incomplete/ambigue, exactement ce que §44 interdit.

Idempotent : peut tourner a chaque demarrage (main.py, apres
assurer_compte_admin) et a chaque assignation de mention
(admin_referentiel_router.assigner_mention_filiere) sans jamais
recreer un cercle deja existant.
"""
import logging
from typing import Optional

from sqlmodel import Session, select

from .models import (
    CercleEtude, Filiere, MembreCercle, RoleMembreCercle, RoleUtilisateur,
    StatutCercle, Utilisateur,
)
from .referentiel import NIVEAUX, libelle_niveau

logger = logging.getLogger("mahay.cercles_referentiel")


def _createur_systeme(session: Session) -> Optional[Utilisateur]:
    """Premier compte admin trouve : sert de createur_id pour les
    cercles generes automatiquement (CercleEtude.createur_id n'est pas
    nullable). None si aucun admin n'existe encore au moment de
    l'appel — l'appelant reporte alors simplement le provisionnement."""
    return session.exec(
        select(Utilisateur).where(Utilisateur.role == RoleUtilisateur.ADMIN)
    ).first()


def assurer_cercles_pour_filiere(session: Session, filiere: Filiere, createur: Utilisateur) -> int:
    """Cree, pour UNE filiere deja rattachee a une mention, le cercle
    manquant pour chaque niveau de NIVEAUX (aucun effet si la filiere
    n'a pas encore de mention). Renvoie le nombre de cercles
    effectivement crees (0 si tous existaient deja)."""
    # Import local : evite tout souci d'import circulaire au chargement
    # du module (cercles_router.py importe deja des choses d'ici a
    # terme) — meme precaution que admin_referentiel_router.py.
    from .routers.cercles_router import _assurer_membres_admins

    if not filiere.mention_id:
        return 0

    niveaux_existants = {
        c.niveau
        for c in session.exec(
            select(CercleEtude).where(
                CercleEtude.mention_id == filiere.mention_id,
                CercleEtude.filiere_id == filiere.id,
                CercleEtude.statut == StatutCercle.ACTIF,
            )
        ).all()
    }

    nb_crees = 0
    for niveau in NIVEAUX:
        if niveau in niveaux_existants:
            continue

        cercle = CercleEtude(
            nom=f"{filiere.nom} — {libelle_niveau(niveau)}",
            mention_id=filiere.mention_id,
            filiere_id=filiere.id,
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


def assurer_cercles_referentiel(session: Session) -> int:
    """Parcourt TOUTES les filieres deja rattachees a une mention et
    garantit qu'un cercle existe pour chacun des 8 niveaux. Appelee au
    demarrage (main.py, apres assurer_compte_admin) et peut etre
    appelee a nouveau sans risque (idempotente). Renvoie le nombre
    total de cercles crees (0 si tout existait deja)."""
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

    total = 0
    for filiere in filieres:
        total += assurer_cercles_pour_filiere(session, filiere, createur)

    if total:
        logger.info("%d cercle(s) national/nationaux provisionne(s) automatiquement.", total)

    return total
