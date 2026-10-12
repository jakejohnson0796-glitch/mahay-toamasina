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

from sqlalchemy import func
from sqlmodel import Session, and_, or_, select

from .models import CercleEtude, Domaine, Faculte, Filiere, Mention, Universite, ProgrammeUniversitaire, RoleUtilisateur, Utilisateur
from .referentiel import NIVEAUX
from .texte_normalise import normaliser as _normaliser_nom_parcours

DELAI_MINIMUM_ENTRE_CHANGEMENTS_NIVEAU = timedelta(days=14)


def offre_filiere_active_universite(session: Session, universite_id: int, filiere_id: int) -> bool:
    """Vrai si le parcours est explicitement offert dans l'universite.

    Une Filiere appartient a la Faculte de son universite. Un lien
    ProgrammeUniversitaire croise ne doit donc jamais rendre ce parcours
    valide dans une autre universite.

    Quand aucune offre n'est encore renseignee pour cette universite (cas
    des anciennes bases/tests), on conserve la compatibilite historique et
    la composante de la Filiere reste la source de rattachement locale.
    Des que des lignes ProgrammeUniversitaire existent pour l'universite,
    une offre active est obligatoire.
    """
    filiere = session.get(Filiere, filiere_id)
    if not filiere:
        return False
    faculte = session.get(Faculte, filiere.faculte_id)
    if not faculte or faculte.universite_id != universite_id:
        return False

    offres_toutes_universites = session.exec(
        select(ProgrammeUniversitaire).where(
            ProgrammeUniversitaire.filiere_id == filiere_id,
        )
    ).all()
    if not offres_toutes_universites:
        return True

    offre_locale = session.exec(
        select(ProgrammeUniversitaire)
        .where(
            ProgrammeUniversitaire.universite_id == universite_id,
            ProgrammeUniversitaire.filiere_id == filiere_id,
            ProgrammeUniversitaire.est_active == True,  # noqa: E712
        )
        .limit(1)
    ).first()
    return offre_locale is not None


def _mention_offerte_dans_faculte(session: Session, mention_id: int, faculte_id: int) -> bool:
    """Verifie que la mention est effectivement representee dans la composante."""
    return session.exec(
        select(Filiere.id)
        .where(
            Filiere.mention_id == mention_id,
            Filiere.faculte_id == faculte_id,
        )
        .limit(1)
    ).first() is not None


def _specialisation_dans_faculte(session: Session, mention_id: int, faculte_id: int, niveau: str) -> bool:
    """Verifie qu'un parcours nomme est explicitement rattache a ce niveau.

    Si l'universite dispose deja de lignes ProgrammeUniversitaire, seule une
    offre active est une preuve de parcours actuellement propose. Tant qu'il
    n'existe aucune offre normalisee pour cette universite, les lignes
    historiques continuent de servir de preuve pour conserver la retrocompatibilite.
    """
    filieres = session.exec(
        select(Filiere).where(
            Filiere.mention_id == mention_id,
            Filiere.faculte_id == faculte_id,
            Filiere.niveau == niveau,
        )
    ).all()
    filieres = [
        f for f in filieres
        if _normaliser_nom_parcours(f.nom) != "tronc commun"
    ]
    if not filieres:
        return False

    faculte = session.get(Faculte, faculte_id)
    if not faculte:
        return False

    offres_universite = session.exec(
        select(ProgrammeUniversitaire.id).where(
            ProgrammeUniversitaire.universite_id == faculte.universite_id,
        )
    ).first()
    if offres_universite is None:
        return True

    return any(
        offre_filiere_active_universite(session, faculte.universite_id, filiere.id)
        for filiere in filieres
    )



def contexte_profil_academique(utilisateur: Utilisateur, session: Session) -> dict:
    """Source de verite unique pour la hierarchie academique d'un utilisateur."""
    if not utilisateur:
        return {
            "universite": None,
            "faculte": None,
            "domaine": None,
            "mention": None,
            "filiere": None,
            "niveau": None,
            "coherent": False,
            "tronc_commun": False,
        }

    universite = session.get(Universite, utilisateur.universite_id) if utilisateur.universite_id else None
    filiere = session.get(Filiere, utilisateur.filiere_id) if utilisateur.filiere_id else None
    # Une ancienne base pouvait avoir matérialisé le tronc commun comme une
    # Filiere technique. Pour le profil métier, cela reste un tronc commun :
    # aucune identité de parcours ne doit être exposée ni utilisée pour les
    # cercles de parcours.
    if filiere and _normaliser_nom_parcours(filiere.nom) == "tronc commun":
        filiere = None
    faculte = (
        session.get(Faculte, utilisateur.faculte_id)
        if utilisateur.faculte_id
        else session.get(Faculte, filiere.faculte_id) if filiere else None
    )
    mention = session.get(Mention, utilisateur.mention_id) if utilisateur.mention_id else None

    # Compatibilite des anciens profils de tronc commun : avant faculte_id,
    # une mention+niveau pouvait etre enregistree sans composante explicite.
    # On ne choisit une composante par defaut que si la mention n'est offerte
    # que par une seule faculte; plusieurs composantes => profil ambigu.
    if faculte is None and mention is not None:
        faculte_ids = {
            f.faculte_id for f in session.exec(
                select(Filiere).where(Filiere.mention_id == mention.id)
            ).all()
            if f.faculte_id
        }
        if len(faculte_ids) == 1:
            faculte = session.get(Faculte, next(iter(faculte_ids)))
    mention_affichee = mention or (
        session.get(Mention, filiere.mention_id)
        if filiere and filiere.mention_id
        else None
    )
    domaine = (
        session.get(Domaine, mention_affichee.domaine_id)
        if mention_affichee and mention_affichee.domaine_id
        else None
    )

    coherent = utilisateur.role not in (RoleUtilisateur.ETUDIANT, RoleUtilisateur.PROFESSEUR)
    if utilisateur.role in (RoleUtilisateur.ETUDIANT, RoleUtilisateur.PROFESSEUR):
        coherent = bool(
            universite
            and universite.est_active
            and faculte
            and mention
            and mention.est_active
            and utilisateur.niveau
            and faculte.universite_id == universite.id
            and (not mention.domaine_id or (domaine and domaine.est_active))
        )

        if coherent and not _mention_offerte_dans_faculte(session, mention.id, faculte.id):
            coherent = False

        if coherent and filiere:
            coherent = bool(
                filiere.faculte_id == faculte.id
                and filiere.mention_id == mention.id
                and (not filiere.niveau or filiere.niveau == utilisateur.niveau)
                and offre_filiere_active_universite(session, universite.id, filiere.id)
            )
        elif coherent and filiere is None:
            if _specialisation_dans_faculte(session, mention.id, faculte.id, utilisateur.niveau):
                coherent = False

    return {
        "universite": universite,
        "faculte": faculte,
        "domaine": domaine,
        "mention": mention_affichee,
        "filiere": filiere,
        "niveau": utilisateur.niveau,
        "coherent": coherent,
        "tronc_commun": bool(
            coherent and filiere is None and mention_affichee and utilisateur.niveau
        ),
    }


def serialiser_profil_academique(profil: dict) -> dict:
    """Contrat JSON canonique hierarchique, avec retrocompatibilite."""
    universite = profil.get("universite")
    faculte = profil.get("faculte")
    domaine = profil.get("domaine")
    mention = profil.get("mention")
    filiere = profil.get("filiere")

    def entite(obj):
        if not obj:
            return None
        data = {"id": obj.id, "nom": obj.nom}
        if isinstance(obj, Universite):
            data["ville"] = obj.ville
        return data

    if not universite or not mention or not profil.get("niveau"):
        type_profil = "incomplet"
    elif filiere is not None:
        type_profil = "parcours"
    else:
        type_profil = "tronc_commun"

    return {
        "type": type_profil,
        "universite": entite(universite),
        "composante": entite(faculte),
        "domaine": entite(domaine),
        "mention": entite(mention),
        "parcours": entite(filiere),
        "niveau": profil.get("niveau"),
        "origine": {
            "universite": universite.nom if universite else None,
            "composante": faculte.nom if faculte else None,
        },
        "formation": {
            "domaine": domaine.nom if domaine else None,
            "mention": mention.nom if mention else None,
            "parcours": "Tronc commun" if profil.get("tronc_commun") else (filiere.nom if filiere else None),
            "niveau": profil.get("niveau"),
        },
        "coherent": bool(profil.get("coherent")),
        "tronc_commun": bool(profil.get("tronc_commun")),
    }

def erreur_choix_academique(
    session: Session, universite_id: Optional[int], faculte_id: Optional[int],
    mention_id: Optional[int], filiere_id: Optional[int], niveau: Optional[str],
    niveaux_valides: set[str],
) -> Optional[str]:
    """Valide une combinaison complete du referentiel avant ecriture."""
    if not (universite_id and faculte_id and mention_id and niveau):
        return "Universite, composante, mention et niveau sont obligatoires."
    if niveau not in niveaux_valides:
        return "Niveau invalide."

    universite = session.get(Universite, universite_id)
    faculte = session.get(Faculte, faculte_id)
    mention = session.get(Mention, mention_id)
    if not universite or not universite.est_active:
        return "Universite invalide ou inactive."
    if not faculte or faculte.universite_id != universite_id:
        return "Composante invalide ou hors de l'universite selectionnee."
    if not mention or not mention.est_active:
        return "Mention invalide ou inactive."
    if not _mention_offerte_dans_faculte(session, mention_id, faculte_id):
        return "Cette mention n'est pas referencee dans la composante selectionnee."

    if filiere_id:
        filiere = session.get(Filiere, filiere_id)
        if not filiere:
            return "Parcours introuvable."
        if filiere.faculte_id != faculte_id:
            return "Ce parcours ne correspond pas a la composante selectionnee."
        if filiere.mention_id != mention_id:
            return "Ce parcours ne correspond pas a la mention selectionnee."
        if filiere.niveau and filiere.niveau != niveau:
            return "Ce parcours n'est pas propose a ce niveau."
        if not offre_filiere_active_universite(session, universite_id, filiere.id):
            return "Ce parcours n'est pas actuellement propose dans cette universite."
        return None

    if _specialisation_dans_faculte(session, mention_id, faculte_id, niveau):
        return "Un parcours specifique existe pour cette mention et ce niveau : selectionnez-le."
    return None

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


def filiere_canonique_pour_cercle(
    session: Session, filiere: Filiere, niveau: Optional[str] = None
) -> Filiere:
    """Choisit le représentant national pour un parcours et un niveau précis.

    Un même intitulé peut exister à plusieurs niveaux. Une ligne dont le
    niveau est NULL est héritée et ne doit jamais remplacer une offre datée
    pour le niveau demandé. Elle ne sert de repli que si aucune ligne exacte
    n'est encore disponible.
    """
    if not filiere.mention_id:
        return filiere

    if niveau and filiere.niveau and filiere.niveau != niveau:
        return filiere

    niveau_cible = niveau or filiere.niveau
    nom_normalise = _normaliser_nom_parcours(filiere.nom)
    candidates = []
    for candidate in session.exec(
        select(Filiere).where(Filiere.mention_id == filiere.mention_id)
    ).all():
        if _normaliser_nom_parcours(candidate.nom) != nom_normalise:
            continue
        if niveau_cible:
            if candidate.niveau is not None and candidate.niveau != niveau_cible:
                continue
        elif candidate.niveau is not None:
            # Sans niveau de référence, ne pas amalgamer plusieurs niveaux
            # partageant le même nom (ex. CCA L3 et CCA M1).
            continue
        faculte = session.get(Faculte, candidate.faculte_id)
        if not faculte or not faculte.universite_id:
            continue
        if not offre_filiere_active_universite(session, faculte.universite_id, candidate.id):
            continue
        candidates.append(candidate)

    if not candidates:
        return filiere

    if niveau_cible:
        candidates_exacts = [candidate for candidate in candidates if candidate.niveau == niveau_cible]
        if candidates_exacts:
            return min(candidates_exacts, key=lambda candidate: candidate.id)
        candidates_heritage = [candidate for candidate in candidates if candidate.niveau is None]
        if candidates_heritage:
            return min(candidates_heritage, key=lambda candidate: candidate.id)

    return min(candidates, key=lambda candidate: candidate.id)


def _filieres_equivalentes(
    session: Session, filiere: Filiere, niveau: Optional[str] = None
) -> list[int]:
    """Renvoie les identifiants de parcours nationaux équivalents au même niveau.

    Le niveau peut provenir du cercle/profil si la ligne Filiere est héritée
    (niveau NULL). Dans ce cas seules les lignes héritées et celles du niveau
    explicitement demandé sont considérées ; deux niveaux explicites ne sont
    jamais fusionnés au seul motif qu'ils ont le même nom.
    """
    if not filiere.mention_id:
        return [filiere.id]

    if niveau and filiere.niveau and filiere.niveau != niveau:
        return []

    niveau_cible = niveau or filiere.niveau
    nom_normalise = _normaliser_nom_parcours(filiere.nom)
    return [
        candidate.id for candidate in session.exec(
            select(Filiere).where(Filiere.mention_id == filiere.mention_id)
        ).all()
        if _normaliser_nom_parcours(candidate.nom) == nom_normalise
        and (
            candidate.niveau is None
            or (niveau_cible is not None and candidate.niveau == niveau_cible)
        )
    ]


def type_cercle(cercle: CercleEtude, mention_effective_id: Optional[int] = None) -> str:
    """Classifie un cercle selon sa hierarchie academique normalisee.

    mention_effective_id sert uniquement a la lecture des anciennes lignes
    dont CercleEtude.mention_id est NULL mais dont le parcours conserve une
    mention valide. La source reste le referentiel Filiere, jamais le nom du cercle.

    libre        : aucun attribut academique ;
    tronc_commun : mention + niveau, sans parcours ;
    parcours     : mention + parcours + niveau ;
    incomplet    : combinaison partielle/incoherente a revoir.
    """
    mention_id = cercle.mention_id or mention_effective_id
    if not mention_id and not cercle.filiere_id and not cercle.niveau:
        return "libre"
    if mention_id and cercle.niveau and not cercle.filiere_id:
        return "tronc_commun"
    if mention_id and cercle.filiere_id and cercle.niveau:
        return "parcours"
    return "incomplet"


def type_cercle_avec_filiere(cercle: CercleEtude, filiere: Optional[Filiere]) -> str:
    """Classifie un cercle en controlant son lien reel au referentiel.

    Les cercles historiques peuvent ne pas avoir mention_id rempli : si leur
    filiere porte bien une mention, on derive cette mention plutot que de les
    afficher comme incomplets. Une filiere absente, sans mention, ou
    contradictoire avec la mention enregistree reste un cas a verifier.
    """
    if not cercle.filiere_id:
        return type_cercle(cercle)

    if not filiere or filiere.id != cercle.filiere_id or not filiere.mention_id:
        return "incomplet"
    if cercle.mention_id and cercle.mention_id != filiere.mention_id:
        return "incomplet"
    if filiere.niveau is not None and filiere.niveau != cercle.niveau:
        # Un niveau explicite dans le referentiel prime sur le nom du cercle ;
        # ne pas afficher comme valide une ligne qui sera refusee a l'adhesion.
        return "incomplet"
    return type_cercle(cercle, mention_effective_id=filiere.mention_id)


def cercle_est_national(cercle: CercleEtude) -> bool:
    """Vrai uniquement pour les cercles nationaux complets declares explicitement."""
    return type_cercle(cercle) in {"tronc_commun", "parcours"}


def cercle_est_national_avec_filiere(cercle: CercleEtude, filiere: Optional[Filiere]) -> bool:
    """Version tenant compte des anciens cercles dont la mention est derivee."""
    return type_cercle_avec_filiere(cercle, filiere) in {"tronc_commun", "parcours"}


def parcours_cercle_offert(
    session: Session,
    mention_id: Optional[int],
    filiere_id: Optional[int],
    niveau: Optional[str],
) -> bool:
    """Vrai si un cercle de parcours correspond a une offre academique reelle."""
    if not mention_id or not filiere_id or not niveau:
        return False

    filiere_reference = session.get(Filiere, filiere_id)
    if not filiere_reference or filiere_reference.mention_id != mention_id:
        return False

    for filiere_id_equivalent in _filieres_equivalentes(session, filiere_reference, niveau=niveau):
        filiere = session.get(Filiere, filiere_id_equivalent)
        if not filiere or filiere.mention_id != mention_id:
            continue
        if filiere.niveau is not None and filiere.niveau != niveau:
            continue
        faculte = session.get(Faculte, filiere.faculte_id)
        if not faculte or not faculte.universite_id:
            continue
        if offre_filiere_active_universite(session, faculte.universite_id, filiere.id):
            return True
    return False


def erreur_cercle_parcours(
    session: Session,
    mention_id: Optional[int],
    filiere_id: Optional[int],
    niveau: Optional[str],
) -> Optional[str]:
    """Valide un triplet Mention + Parcours + Niveau avant creation/approbation."""
    if not (mention_id and filiere_id and niveau):
        return "Mention, parcours et niveau sont obligatoires."
    if niveau not in NIVEAUX:
        return "Niveau invalide."

    filiere = session.get(Filiere, filiere_id)
    if not filiere:
        return "Parcours introuvable."
    if filiere.mention_id != mention_id:
        return "Ce parcours ne correspond pas a la mention selectionnee."
    if filiere.niveau is not None and filiere.niveau != niveau:
        return "Ce parcours n'est pas propose a ce niveau."
    if not parcours_cercle_offert(session, mention_id, filiere_id, niveau):
        return "Ce parcours n'est pas actuellement propose a ce niveau."
    return None


def tronc_commun_offert(
    session: Session,
    universite_id: Optional[int],
    faculte_id: Optional[int],
    mention_id: Optional[int],
    niveau: Optional[str],
) -> bool:
    """Vrai si la combinaison mention+niveau peut exister en tronc commun
    dans la composante de l'universite.

    Aucun niveau ne doit etre deduit. Le tronc commun est possible seulement
    si la mention est active et presente dans la composante, et si aucun
    parcours actuellement offert ne couvre deja ce niveau.
    """
    if not universite_id or not faculte_id or not mention_id or not niveau:
        return False
    if niveau not in NIVEAUX:
        return False

    universite = session.get(Universite, universite_id)
    faculte = session.get(Faculte, faculte_id)
    mention = session.get(Mention, mention_id)
    if (
        not universite
        or not faculte
        or faculte.universite_id != universite.id
        or not mention
        or not getattr(mention, "est_active", True)
    ):
        return False

    if not _mention_offerte_dans_faculte(session, mention_id, faculte_id):
        return False

    return not _specialisation_dans_faculte(
        session, mention_id, faculte_id, niveau
    )


def profil_correspond_au_cercle(utilisateur: Utilisateur, cercle: CercleEtude, session: Session) -> bool:
    """Test canonique d'eligibilite, y compris pour les cercles historiques."""
    filiere_cercle = (
        session.get(Filiere, cercle.filiere_id) if cercle.filiere_id else None
    )
    nature = type_cercle_avec_filiere(cercle, filiere_cercle)
    if nature == "libre":
        return True
    if nature == "incomplet":
        return False

    mention_id_effectif = cercle.mention_id or (
        filiere_cercle.mention_id if filiere_cercle else None
    )
    if nature == "parcours" and not parcours_cercle_offert(
        session, mention_id_effectif, cercle.filiere_id, cercle.niveau
    ):
        return False

    profil = contexte_profil_academique(utilisateur, session)
    if not profil["coherent"]:
        return False

    mention = profil["mention"]
    if not mention or mention.id != mention_id_effectif or profil["niveau"] != cercle.niveau:
        return False

    if nature == "tronc_commun":
        return True

    filiere_utilisateur = profil["filiere"]
    if not filiere_utilisateur:
        return False
    return cercle.filiere_id in _filieres_equivalentes(session, filiere_utilisateur, niveau=cercle.niveau)


def condition_cercles_disponibles(
    utilisateur: Optional[Utilisateur], session: Session, profil: Optional[dict] = None
):
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
    cercle_libre = and_(
        CercleEtude.mention_id.is_(None),
        CercleEtude.filiere_id.is_(None),
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

    filieres_equivalentes = _filieres_equivalentes(session, filiere_utilisateur, niveau=utilisateur.niveau)

    # Les cercles legacy peuvent avoir mention_id=NULL alors que la filiere
    # rattachee possede une mention. Une sous-requete correlee permet de
    # comparer la mention effective sans ajouter une jointure implicite qui
    # ferait un produit cartesien chez les appelants de cette condition.
    mention_filiere_sql = (
        select(Filiere.mention_id)
        .where(Filiere.id == CercleEtude.filiere_id)
        .correlate(CercleEtude)
        .scalar_subquery()
    )
    mention_effective_sql = func.coalesce(CercleEtude.mention_id, mention_filiere_sql)
    niveau_filiere_sql = (
        select(Filiere.niveau)
        .where(Filiere.id == CercleEtude.filiere_id)
        .scalar_subquery()
    )
    mentions_coherentes = or_(
        CercleEtude.mention_id.is_(None),
        CercleEtude.mention_id == mention_filiere_sql,
    )
    niveaux_coherents = or_(
        niveau_filiere_sql.is_(None),
        niveau_filiere_sql == CercleEtude.niveau,
    )

    return or_(
        cercle_libre,
        cercle_tronc_commun_correspondant,
        and_(
            mention_effective_sql == mention_id,
            CercleEtude.filiere_id.in_(filieres_equivalentes),
            CercleEtude.niveau == utilisateur.niveau,
            mentions_coherentes,
            niveaux_coherents,
        ),
    )
