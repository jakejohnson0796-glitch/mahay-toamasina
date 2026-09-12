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

from .models import CercleEtude, Filiere, RoleUtilisateur, Utilisateur
from .texte_normalise import normaliser as _normaliser_nom_parcours

DELAI_MINIMUM_ENTRE_CHANGEMENTS_NIVEAU = timedelta(days=14)


def profil_academique_incomplet(utilisateur: Utilisateur, session: Session) -> bool:
    """§21-22 du brief : vrai si ce compte a besoin du statut
    PROFILE_ACADEMIC_UPDATE_REQUIRED. Concerne les comptes ETUDIANT et
    PROFESSEUR (les deux ont un parcours academique a declarer — un
    professeur anime des cours dans un contexte universite/filiere
    donne, voir Classe virtuelle) : un sponsor/repetiteur ou un admin
    n'a pas de parcours academique a declarer (voir la meme exemption a
    l'inscription, auth_router.py).

    Depuis l'ajout de Filiere.niveau et Utilisateur.mention_id (rapport
    du 10/09/2026) : universite, mention et niveau sont toujours
    requis, mais filiere_id ne l'est PAS pour un etudiant en tronc
    commun -- valide tant qu'aucune Filiere nommee n'existe encore pour
    son (mention, niveau). Des qu'au moins une existe, il doit en
    choisir une (le champ redevient obligatoire a ce niveau-la)."""
    if utilisateur.role not in (RoleUtilisateur.ETUDIANT, RoleUtilisateur.PROFESSEUR):
        return False

    if not (utilisateur.universite_id and utilisateur.mention_id and utilisateur.niveau):
        return True

    if utilisateur.filiere_id:
        filiere = session.get(Filiere, utilisateur.filiere_id)
        if not filiere or not filiere.faculte or filiere.faculte.universite_id != utilisateur.universite_id:
            return True
        if filiere.mention_id and filiere.mention_id != utilisateur.mention_id:
            return True
        if filiere.niveau and filiere.niveau != utilisateur.niveau:
            return True
        return False

    # Pas de filiere choisie : valide UNIQUEMENT si c'est reellement du
    # tronc commun, c'est-a-dire si aucun parcours nomme n'existe pour
    # cette mention a ce niveau (deduit des donnees, jamais code en dur
    # -- un meme niveau peut etre tronc commun pour une mention et deja
    # specialise pour une autre, voir le rapport).
    existe_une_specialisation = session.exec(
        select(Filiere.id).where(
            Filiere.mention_id == utilisateur.mention_id,
            Filiere.niveau == utilisateur.niveau,
        )
    ).first()
    return existe_une_specialisation is not None


def cercle_est_national(cercle: CercleEtude) -> bool:
    """Un cercle 'libre' (mention_id ou niveau manquant) n'est soumis a
    aucune des regles ci-dessous — il continue de fonctionner exactement
    comme avant cette evolution. Un cercle avec mention_id + niveau EST
    deja national/restreint, que filiere_id soit renseigne (cercle scope
    a un parcours precis) ou non (cercle de tronc commun, scope
    mention+niveau uniquement -- voir le rapport du 10/09/2026 sur
    Filiere.niveau)."""
    return bool(cercle.mention_id and cercle.niveau)


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
        if _normaliser_nom_parcours(f.nom) == nom_normalise and f.niveau == filiere.niveau
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

    if not utilisateur.mention_id or not utilisateur.niveau:
        return False
    if utilisateur.mention_id != cercle.mention_id or utilisateur.niveau != cercle.niveau:
        return False

    if not cercle.filiere_id:
        # Cercle de tronc commun (mention+niveau, sans parcours precis) :
        # correspond a tout etudiant de cette mention/niveau, qu'il ait
        # deja choisi une filiere specifique ou non.
        return True

    if not utilisateur.filiere_id:
        return False
    filiere_utilisateur = session.get(Filiere, utilisateur.filiere_id)
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

    if utilisateur is None or not utilisateur.mention_id or not utilisateur.niveau:
        return cercle_libre

    # Cercle de tronc commun pour la mention+niveau de l'utilisateur :
    # correspond qu'il ait deja choisi une filiere ou non (voir
    # profil_correspond_au_cercle).
    cercle_tronc_commun_correspondant = and_(
        CercleEtude.mention_id == utilisateur.mention_id,
        CercleEtude.niveau == utilisateur.niveau,
        CercleEtude.filiere_id.is_(None),
    )

    if not utilisateur.filiere_id:
        return or_(cercle_libre, cercle_tronc_commun_correspondant)

    filiere_utilisateur = session.get(Filiere, utilisateur.filiere_id)
    if not filiere_utilisateur:
        return or_(cercle_libre, cercle_tronc_commun_correspondant)

    filieres_equivalentes = _filieres_equivalentes(session, filiere_utilisateur)

    return or_(
        cercle_libre,
        cercle_tronc_commun_correspondant,
        and_(
            CercleEtude.mention_id == utilisateur.mention_id,
            CercleEtude.filiere_id.in_(filieres_equivalentes),
            CercleEtude.niveau == utilisateur.niveau,
        ),
    )
