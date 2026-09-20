"""
Logique metier du referentiel academique national — centralisee ici
pour etre testable independamment des routes FastAPI (qui ne font que
l'orchestration HTTP) et reutilisable partout ou elle est necessaire
(cercles_router.py, auth_router.py, futurs ecrans admin).

Regles implementees (voir le brief "cercles nationaux") :
- §14 : le niveau ne peut etre modifie qu'une fois tous les 14 jours,
  controle cote backend (le frontend n'est jamais la seule protection) ;
- §21-22 : un compte etudiant existant dont le profil academique est
  incomplet ou incoherent doit recevoir un statut
  PROFILE_ACADEMIC_UPDATE_REQUIRED (voir profil_academique_incomplet
  ci-dessous) et une notification claire jusqu'a actualisation ;
- §31-32 : un cercle "national" (mention_id + filiere_id + niveau tous
  renseignes) n'accepte que les etudiants dont le profil correspond
  exactement aux 3 ; la verification doit etre refaite au moment de
  l'action (demande ET approbation), pas seulement a la creation de la
  demande, pour couvrir le cas ou l'etudiant change de niveau entre-temps.
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, and_, or_, select

from .models import CercleEtude, Domaine, Faculte, Filiere, Mention, Universite, RoleUtilisateur, Utilisateur
from .texte_normalise import normaliser as _normaliser_nom_parcours

DELAI_MINIMUM_ENTRE_CHANGEMENTS_NIVEAU = timedelta(days=14)


def contexte_profil_academique(utilisateur: Utilisateur, session: Session) -> dict:
    """Source de verite unique pour l'identite academique.

    Ordre hierarchique : Universite -> Composante -> Domaine -> Mention
    -> Parcours -> Niveau. ``coherent`` indique si le profil est assez
    fiable pour les regles des cercles nationaux.
    """
    if not utilisateur:
        return {"universite": None, "faculte": None, "domaine": None, "mention": None,
                "filiere": None, "niveau": None, "coherent": False, "tronc_commun": False}

    universite = session.get(Universite, utilisateur.universite_id) if utilisateur.universite_id else None
    filiere = session.get(Filiere, utilisateur.filiere_id) if utilisateur.filiere_id else None
    faculte = session.get(Faculte, filiere.faculte_id) if filiere else None
    mention = session.get(Mention, utilisateur.mention_id) if utilisateur.mention_id else None
    mention_affichee = mention or (session.get(Mention, filiere.mention_id) if filiere and filiere.mention_id else None)
    domaine = session.get(Domaine, mention_affichee.domaine_id) if mention_affichee and mention_affichee.domaine_id else None

    coherent = utilisateur.role not in (RoleUtilisateur.ETUDIANT, RoleUtilisateur.PROFESSEUR)
    if utilisateur.role in (RoleUtilisateur.ETUDIANT, RoleUtilisateur.PROFESSEUR):
        coherent = bool(universite and universite.est_active and mention and mention.est_active and utilisateur.niveau)
        if coherent and filiere:
            coherent = bool(
                faculte and faculte.universite_id == universite.id
                and filiere.mention_id == mention.id
                and (not filiere.niveau or filiere.niveau == utilisateur.niveau)
            )
        if coherent and filiere is None:
            existe_une_specialisation = session.exec(select(Filiere.id).where(
                Filiere.mention_id == mention.id,
                Filiere.niveau == utilisateur.niveau,
            )).first()
            coherent = existe_une_specialisation is None

    return {
        "universite": universite, "faculte": faculte, "domaine": domaine,
        "mention": mention_affichee, "filiere": filiere, "niveau": utilisateur.niveau,
        "coherent": coherent,
        "tronc_commun": bool(coherent and filiere is None and mention_affichee and utilisateur.niveau),
    }
def profil_academique_incomplet(utilisateur: Utilisateur, session: Session) -> bool:
    """Vrai si le profil academique ne peut pas servir de reference fiable."""
    if utilisateur.role not in (RoleUtilisateur.ETUDIANT, RoleUtilisateur.PROFESSEUR):
        return False
    return not contexte_profil_academique(utilisateur, session)["coherent"]

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


def _filieres_equivalentes(session: Session, filiere: Filiere) -> list[int]:
    """Renvoie les id de TOUTES les Filiere qui representent le meme
    parcours national que `filiere` — meme mention_id + meme nom une
    fois normalise + meme niveau (deux niveaux differents du meme nom,
    ex. "CCA" en M1 et M2, sont deux parcours distincts, voir
    Filiere.niveau), potentiellement rattachees a d'autres universites
    (voir cercles_referentiel.py pour le contexte complet : Filiere est
    scopee par universite, donc le meme parcours a une ligne differente
    par universite qui l'offre).

    Necessaire ici parce qu'un cercle national ne reference qu'UNE
    seule Filiere representante (cercles_referentiel.py en choisit une
    arbitrairement pour le groupe) — un etudiant dont la propre
    filiere_id pointe vers une AUTRE Filiere du meme groupe doit quand
    meme etre reconnu comme correspondant au cercle, sinon les
    etudiants de toutes les universites sauf celle de la representante
    ne pourraient jamais rejoindre leur propre cercle national."""
    if not filiere.mention_id:
        return [filiere.id]
    nom_normalise = _normaliser_nom_parcours(filiere.nom)
    return [
        f.id for f in session.exec(
            select(Filiere).where(Filiere.mention_id == filiere.mention_id)
        ).all()
        if _normaliser_nom_parcours(f.nom) == nom_normalise and (f.niveau is None or f.niveau == filiere.niveau)
    ]


def profil_correspond_au_cercle(utilisateur: Utilisateur, cercle: CercleEtude, session: Session) -> bool:
    """§31 : verifie mention + niveau, et le parcours (national, pas
    juste filiere_id brut — voir _filieres_equivalentes ci-dessus)
    quand le cercle en exige un. Utilisateur.mention_id (voir le
    rapport du 10/09/2026) est desormais la source de verite pour la
    mention -- plus besoin de la deduire de filiere_id, ce qui permet a
    un etudiant en tronc commun (filiere_id vide) de correspondre a un
    cercle de mention+niveau."""
    if not cercle_est_national(cercle):
        # Cercle libre : aucune restriction, comme avant cette evolution.
        return True

    profil = contexte_profil_academique(utilisateur, session)
    if not profil["coherent"]:
        return False
    mention = profil["mention"]
    if not mention or mention.id != cercle.mention_id or profil["niveau"] != cercle.niveau:
        return False
    if not cercle.filiere_id:
        return True
    filiere_utilisateur = profil["filiere"]
    if not filiere_utilisateur:
        return False
    return cercle.filiere_id in _filieres_equivalentes(session, filiere_utilisateur)


def condition_cercles_disponibles(utilisateur: Optional[Utilisateur], session: Session):
    """Condition SQLAlchemy (a passer a .where()) qui identifie les
    cercles 'disponibles' pour cet utilisateur, au meme sens que
    profil_correspond_au_cercle ci-dessus : les cercles libres, plus le
    cercle de tronc commun de sa mention+niveau s'il existe, plus — s'il
    a deja choisi une filiere — le cercle national de son parcours
    (base sur le parcours national, pas juste sa propre Filiere.id —
    voir _filieres_equivalentes).

    Construite cote SQL (plutot qu'evaluee ligne par ligne en Python
    apres avoir tout charge) pour rester efficace meme avec un grand
    nombre de cercles en base (voir cercles_referentiel.py, qui peut en
    generer plusieurs centaines — un par parcours x niveau). La seule
    partie Python est le calcul, une fois, de la liste des Filiere
    equivalentes au parcours de l'utilisateur — necessairement en
    Python puisque la normalisation (accents/casse) n'est pas
    exprimable simplement en SQL portable SQLite/Postgres.

    Utilisateur non connecte, ou sans mention/niveau declares : seuls
    les cercles libres sont consideres disponibles (il ne peut, de toute
    facon, rejoindre aucun cercle national tant que son profil n'est pas
    complet — voir la meme regle dans profil_correspond_au_cercle)."""
    cercle_libre = or_(
        CercleEtude.mention_id.is_(None),
        CercleEtude.niveau.is_(None),
    )

    if utilisateur is None or not utilisateur.niveau:
        return cercle_libre

    profil = contexte_profil_academique(utilisateur, session)
    if not profil["coherent"]:
        return cercle_libre

    mention_id = profil["mention"].id
    filiere_utilisateur = profil["filiere"]

    # Cercle de tronc commun pour la mention+niveau de l'utilisateur :
    # correspond qu'il ait deja choisi une filiere ou non (voir
    # profil_correspond_au_cercle).
    cercle_tronc_commun_correspondant = and_(
        CercleEtude.mention_id == mention_id,
        CercleEtude.niveau == utilisateur.niveau,
        CercleEtude.filiere_id.is_(None),
    )

    if not utilisateur.filiere_id:
        return or_(cercle_libre, cercle_tronc_commun_correspondant)

    if not filiere_utilisateur:
        return or_(cercle_libre, cercle_tronc_commun_correspondant)

    filieres_equivalentes = _filieres_equivalentes(session, filiere_utilisateur)

    return or_(
        cercle_libre,
        cercle_tronc_commun_correspondant,
        and_(
            CercleEtude.mention_id == mention_id,
            CercleEtude.filiere_id.in_(filieres_equivalentes),
            CercleEtude.niveau == utilisateur.niveau,
        ),
    )
