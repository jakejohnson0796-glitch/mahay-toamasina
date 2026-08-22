"""
Logique metier du referentiel academique national — centralisee ici
pour etre testable independamment des routes FastAPI (qui ne font que
l'orchestration HTTP) et reutilisable partout ou elle est necessaire
(cercles_router.py, auth_router.py, futurs ecrans admin).

Regles implementees (voir le brief "cercles nationaux") :
- §14 : le niveau ne peut etre modifie qu'une fois tous les 14 jours,
  controle cote backend (le frontend n'est jamais la seule protection) ;
- §31-32 : un cercle "national" (mention_id + filiere_id + niveau tous
  renseignes) n'accepte que les etudiants dont le profil correspond
  exactement aux 3 ; la verification doit etre refaite au moment de
  l'action (demande ET approbation), pas seulement a la creation de la
  demande, pour couvrir le cas ou l'etudiant change de niveau entre-temps.
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, and_, or_

from .models import CercleEtude, Filiere, Utilisateur

DELAI_MINIMUM_ENTRE_CHANGEMENTS_NIVEAU = timedelta(days=14)


def cercle_est_national(cercle: CercleEtude) -> bool:
    """Un cercle 'libre' (au moins un des 3 champs manquant) n'est
    soumis a aucune des regles ci-dessous — il continue de fonctionner
    exactement comme avant cette evolution."""
    return bool(cercle.mention_id and cercle.filiere_id and cercle.niveau)


def prochain_changement_niveau_autorise_le(utilisateur: Utilisateur) -> Optional[datetime]:
    """None si l'utilisateur peut changer son niveau des maintenant
    (jamais modifie, ou delai ecoule). Sinon, la date/heure a partir de
    laquelle ce sera de nouveau possible."""
    if utilisateur.niveau_modifie_le is None:
        return None
    echeance = utilisateur.niveau_modifie_le + DELAI_MINIMUM_ENTRE_CHANGEMENTS_NIVEAU
    if datetime.utcnow() >= echeance:
        return None
    return echeance


def peut_modifier_niveau_maintenant(utilisateur: Utilisateur) -> bool:
    return prochain_changement_niveau_autorise_le(utilisateur) is None


def jours_avant_prochain_changement_niveau(utilisateur: Utilisateur) -> int:
    """Nombre de jours (arrondi au superieur) avant le prochain
    changement autorise. 0 si deja autorise maintenant."""
    echeance = prochain_changement_niveau_autorise_le(utilisateur)
    if echeance is None:
        return 0
    restant = echeance - datetime.utcnow()
    # +86399 secondes avant division entiere = arrondi au jour superieur
    # (1h restante doit afficher "1 jour", pas "0 jour" qui laisserait
    # croire que c'est deja possible).
    return max(1, int((restant.total_seconds() + 86399) // 86400))


def profil_correspond_au_cercle(utilisateur: Utilisateur, cercle: CercleEtude, session: Session) -> bool:
    """§31 : vérifie mention + filiere + niveau. La mention de
    l'utilisateur se deduit de sa filiere (Filiere.mention_id), un
    Utilisateur n'a pas de mention_id propre — sa filiere EST sa
    mention, par construction (§6 : une filiere appartient a une seule
    mention)."""
    if not cercle_est_national(cercle):
        # Cercle libre : aucune restriction, comme avant cette evolution.
        return True

    if not utilisateur.filiere_id or not utilisateur.niveau:
        return False

    filiere_utilisateur = session.get(Filiere, utilisateur.filiere_id)
    if not filiere_utilisateur:
        return False

    return (
        filiere_utilisateur.mention_id == cercle.mention_id
        and utilisateur.filiere_id == cercle.filiere_id
        and utilisateur.niveau == cercle.niveau
    )


def condition_cercles_disponibles(utilisateur: Optional[Utilisateur], session: Session):
    """Condition SQLAlchemy (a passer a .where()) qui identifie les
    cercles 'disponibles' pour cet utilisateur, au meme sens que
    profil_correspond_au_cercle ci-dessus : les cercles libres, plus —
    si son profil filiere+niveau est complet — le seul cercle national
    qui lui correspond exactement.

    Construite cote SQL (plutot qu'evaluee ligne par ligne en Python
    apres avoir tout charge) pour rester efficace meme avec un grand
    nombre de cercles en base (voir cercles_referentiel.py, qui peut en
    generer plusieurs centaines — un par filiere x niveau).

    Utilisateur non connecte, ou profil filiere/niveau incomplet : seuls
    les cercles libres sont consideres disponibles (il ne peut, de toute
    facon, rejoindre aucun cercle national tant que son profil n'est pas
    complet — voir la meme regle dans profil_correspond_au_cercle)."""
    cercle_libre = or_(
        CercleEtude.mention_id.is_(None),
        CercleEtude.filiere_id.is_(None),
        CercleEtude.niveau.is_(None),
    )

    if utilisateur is None or not utilisateur.filiere_id or not utilisateur.niveau:
        return cercle_libre

    filiere_utilisateur = session.get(Filiere, utilisateur.filiere_id)
    if not filiere_utilisateur:
        return cercle_libre

    return or_(
        cercle_libre,
        and_(
            CercleEtude.mention_id == filiere_utilisateur.mention_id,
            CercleEtude.filiere_id == utilisateur.filiere_id,
            CercleEtude.niveau == utilisateur.niveau,
        ),
    )
