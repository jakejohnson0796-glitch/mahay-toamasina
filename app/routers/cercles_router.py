"""
Cercles d'etude : salons de discussion pour que les etudiants s'entraident
et revisent ensemble, en plus du depot de documents. Chat en temps reel
via WebSocket FastAPI natif (pas de service tiers) : ca reste 100% Python
et coherent avec le reste du projet (voir README, section "choix
techniques" — pas de framework JS pour ce MVP).

L'authentification du WebSocket reutilise directement le cookie de session
existant (SessionMiddleware, deja installe dans main.py) : pas besoin de
mecanisme separe, Starlette applique cette middleware aussi bien aux
requetes HTTP classiques qu'aux connexions WebSocket.
"""
from typing import Optional
from datetime import datetime
from urllib.parse import urlencode
import re

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import RedirectResponse, FileResponse
from sqlalchemy import case
from sqlmodel import Session, select, or_, func

from ..database import get_session, engine
from ..templating import templates
from ..csrf import verifier_csrf
from ..models import (
    CercleEtude, Domaine, MembreCercle, MessageCercle, SignalementMessage, Filiere, Mention, Universite, Utilisateur,
    RoleUtilisateur, RoleMembreCercle, DemandeAdhesionCercle, StatutDemandeAdhesion, DemandeCreationCercle,
    StatutDemandeCreationCercle, StatutCercle, ThemeDuJour, Document,
    MessageReaction, TypeReaction, MessageMention, Notification, TypeNotification,
)
from ..auth import utilisateur_courant
from ..ws_manager import gestionnaire
from ..dependencies import acces_premium_ou_redirection
from ..storage import sauvegarder_fichier, obtenir_url_telechargement, stockage_distant_actif, FichierInvalide, supprimer_fichier
from .. import subscription
from .. import theme_service
from .. import referentiel_academique
from ..web_utils import entier_ou_none
from ..referentiel import NIVEAUX
from ..recherche import clause_recherche_cercles

router = APIRouter()

LONGUEUR_MAX_MESSAGE = 2000
TAILLE_MAX_PIECE_JOINTE = 10 * 1024 * 1024  # 10 Mo

# Un meme numero de telephone (= un meme compte utilisateur, le telephone
# etant l'identifiant unique de connexion) ne peut creer plus de ce nombre
# de Cercles d'etude. Verifie a chaque creation directement depuis la
# base de donnees (COUNT reel), jamais via un compteur mis en cache qui
# pourrait diverger de l'etat reel (voir creer_cercle ci-dessous).
MAX_CERCLES_PAR_UTILISATEUR = 3

# Motifs de signalement proposes cote interface (voir gabarit cercle_chat.html).
# La valeur "Autre" declenche un champ de saisie libre — voir signaler_message().
MOTIFS_SIGNALEMENT_AUTORISES = {
    "Spam",
    "Harcèlement ou insultes",
    "Contenu inapproprié",
    "Désinformation",
    "Autre",
}


def _a_acces_cercle(session: Session, cercle_id: int, utilisateur_id: int) -> bool:
    """Acces effectif au cercle : membre reel OU administrateur global.

    L'administrateur n'est pas materialise comme membre de chaque cercle :
    cela evite une enorme redondance de lignes MembreCercle et toutes les
    operations d'entretien associees. Les compteurs de membres continuent,
    eux, de compter uniquement les membres reels.
    """
    cercle = session.get(CercleEtude, cercle_id)
    if not cercle or cercle.statut != StatutCercle.ACTIF:
        return False

    return session.exec(
        select(Utilisateur.id)
        .outerjoin(
            MembreCercle,
            (MembreCercle.cercle_id == cercle_id)
            & (MembreCercle.utilisateur_id == Utilisateur.id),
        )
        .where(
            Utilisateur.id == utilisateur_id,
            or_(
                Utilisateur.role == RoleUtilisateur.ADMIN,
                MembreCercle.id.is_not(None),
            ),
        )
    ).first() is not None


def _est_admin(utilisateur: Optional[Utilisateur]) -> bool:
    return bool(utilisateur and utilisateur.role == RoleUtilisateur.ADMIN)


def _peut_gerer_cercle(cercle: CercleEtude, utilisateur: Optional[Utilisateur]) -> bool:
    """Createur du cercle (uniquement le sien) ou admin (n'importe
    lequel), mais uniquement tant que le cercle est ACTIF.

    Un cercle ARCHIVE reste recuperable pour l'historique, mais ne doit
    plus accepter d'actions utilisateur (adhesion, moderation, messages,
    membres, etc.)."""
    if not utilisateur or cercle.statut != StatutCercle.ACTIF:
        return False
    return utilisateur.id == cercle.createur_id or _est_admin(utilisateur)


def _demande_en_attente(session: Session, cercle_id: int, utilisateur_id: int) -> Optional[DemandeAdhesionCercle]:
    return session.exec(
        select(DemandeAdhesionCercle).where(
            DemandeAdhesionCercle.cercle_id == cercle_id,
            DemandeAdhesionCercle.utilisateur_id == utilisateur_id,
            DemandeAdhesionCercle.statut == StatutDemandeAdhesion.EN_ATTENTE,
        )
    ).first()


def _reactions_du_message(session: Session, message_id: int, utilisateur_id: int) -> list[dict]:
    """Compte les reactions d'un message, groupees par type (§4 du brief :
    "👍 5   ❤️ 3   😂 1"), en indiquant si l'utilisateur courant en fait
    partie (utilise cote frontend pour surligner sa propre reaction)."""
    lignes = session.exec(select(MessageReaction).where(MessageReaction.message_id == message_id)).all()
    comptes: dict[str, dict] = {}
    for r in lignes:
        entree = comptes.setdefault(r.type_reaction.value, {"type_reaction": r.type_reaction.value, "total": 0, "mienne": False})
        entree["total"] += 1
        if r.utilisateur_id == utilisateur_id:
            entree["mienne"] = True
    # Ordre stable = ordre des TypeReaction (pas d'ordre d'insertion en base).
    return [comptes[t.value] for t in TypeReaction if t.value in comptes]


def _nombre_reponses(session: Session, message_id: int) -> int:
    """Nombre de reponses directes a un message (§6 : "💬 6 reponses").
    Ne compte pas recursivement les reponses-a-des-reponses : un thread
    reste a un seul niveau de profondeur, comme le reste de l'UX cible
    (Messenger/WhatsApp ne font pas non plus de threads imbriques)."""
    return session.exec(
        select(func.count()).select_from(MessageCercle).where(
            MessageCercle.parent_message_id == message_id,
            MessageCercle.supprime == False,  # noqa: E712
        )
    ).one()


def _derniere_reponse(session: Session, message_id: int) -> Optional[dict]:
    """Reponse la plus recente a un message, pour l'apercu affiche dans le
    flux principal a cote de "💬 N reponses" (§ refonte visuelle du chat
    de cercle) -- un court avant-gout du fil sans avoir a l'ouvrir,
    inspire des messageries type Slack. La bulle complete de la reponse
    reste chargee a la demande via /messages/{id}/thread ; seuls
    l'auteur et un extrait tronque du contenu sortent ici. N'est appelee
    que pour les messages ayant au moins une reponse (voir l'appelant),
    pour ne pas ajouter une requete par message sans fil."""
    ligne = session.exec(
        select(MessageCercle, Utilisateur)
        .where(MessageCercle.parent_message_id == message_id)
        .where(MessageCercle.supprime == False)  # noqa: E712
        .where(MessageCercle.auteur_id == Utilisateur.id)
        .order_by(MessageCercle.date_envoi.desc())
    ).first()
    if not ligne:
        return None
    m, u = ligne
    contenu = m.piece_jointe_nom if m.piece_jointe_chemin else m.contenu
    contenu = contenu or ""
    if len(contenu) > 80:
        contenu = contenu[:79].rstrip() + "…"
    return {"auteur": u.nom, "contenu": contenu}


def _creer_notification(
    session: Session,
    destinataire_id: int,
    type_notification: TypeNotification,
    contenu: str,
    acteur_id: Optional[int] = None,
    cercle_id: Optional[int] = None,
    message_id: Optional[int] = None,
) -> None:
    """Cree une notification, sauf si l'acteur et le destinataire sont la
    meme personne (§11 du brief : "eviter les notifications inutiles" —
    personne n'a besoin d'etre notifie de sa propre action)."""
    if acteur_id is not None and acteur_id == destinataire_id:
        return
    session.add(Notification(
        destinataire_id=destinataire_id,
        type_notification=type_notification,
        contenu=contenu,
        acteur_id=acteur_id,
        cercle_id=cercle_id,
        message_id=message_id,
    ))
    session.commit()


def _supprimer_cercle_et_contenu(session: Session, cercle_id: int) -> bool:
    """Supprime un cercle et ses donnees strictement propres, dans un ordre
    compatible avec les FK Postgres/Supabase.

    Les ressources historiques partageables ne sont pas supprimees :
    - Document.cercle_id est detache (le document reste dans la bibliotheque) ;
    - ThemeDuJour.cercle_id est detache (l'historique du theme est conserve) ;
    - DemandeCreationCercle.cercle_cree_id est detache (l'historique admin reste).
    En revanche, les messages et toutes leurs dependances propres sont
    supprimes, y compris les fichiers joints du chat.
    """
    cercle = session.get(CercleEtude, cercle_id)
    if not cercle:
        return False

    # Cette fonction est un primitive de suppression interne : elle doit
    # aussi pouvoir supprimer un cercle ARCHIVE lors de la suppression
    # administrative de son createur. Les routes utilisateur, elles,
    # imposent ACTIF avant d'appeler cette primitive.
    message_ids = [
        m.id for m in session.exec(
            select(MessageCercle).where(MessageCercle.cercle_id == cercle_id)
        ).all()
    ]

    # Dependances des messages avant suppression des messages eux-memes.
    if message_ids:
        for signalement in session.exec(
            select(SignalementMessage).where(SignalementMessage.message_id.in_(message_ids))
        ).all():
            session.delete(signalement)
        for reaction in session.exec(
            select(MessageReaction).where(MessageReaction.message_id.in_(message_ids))
        ).all():
            session.delete(reaction)
        for mention in session.exec(
            select(MessageMention).where(MessageMention.message_id.in_(message_ids))
        ).all():
            session.delete(mention)
        for notification in session.exec(
            select(Notification).where(Notification.message_id.in_(message_ids))
        ).all():
            session.delete(notification)

    # Les notifications directement rattachees au cercle, sans message.
    for notification in session.exec(
        select(Notification).where(Notification.cercle_id == cercle_id)
    ).all():
        session.delete(notification)

    # Les documents restent dans la bibliotheque generale.
    for document in session.exec(
        select(Document).where(Document.cercle_id == cercle_id)
    ).all():
        document.cercle_id = None
        session.add(document)

    # L'historique des demandes de creation reste en base.
    for demande_creation in session.exec(
        select(DemandeCreationCercle).where(DemandeCreationCercle.cercle_cree_id == cercle_id)
    ).all():
        demande_creation.cercle_cree_id = None
        session.add(demande_creation)

    # L'historique des themes reste en base ; seul le lien vers le cercle disparait.
    for theme_jour in session.exec(
        select(ThemeDuJour).where(ThemeDuJour.cercle_id == cercle_id)
    ).all():
        theme_jour.cercle_id = None
        session.add(theme_jour)

    # Suppression des messages : les reponses sont effacees avant les parents
    # pour eviter toute violation de la FK auto-referencee parent_message_id.
    messages = session.exec(
        select(MessageCercle).where(MessageCercle.cercle_id == cercle_id)
    ).all()
    messages_tries = sorted(messages, key=lambda m: 1 if m.parent_message_id else 0)
    for message in messages_tries:
        if message.piece_jointe_chemin:
            try:
                supprimer_fichier(message.piece_jointe_chemin)
            except Exception:
                # Une erreur de nettoyage du stockage ne doit pas empecher
                # la suppression logique du cercle en base.
                pass
        session.delete(message)

    for demande in session.exec(
        select(DemandeAdhesionCercle).where(DemandeAdhesionCercle.cercle_id == cercle_id)
    ).all():
        session.delete(demande)

    for membre in session.exec(
        select(MembreCercle).where(MembreCercle.cercle_id == cercle_id)
    ).all():
        session.delete(membre)

    session.delete(cercle)
    return True


@router.get("/cercles")
def liste_cercles(
    request: Request,
    q: Optional[str] = None,
    domaine_id: Optional[str] = None,
    mention_id: Optional[str] = None,
    filiere_id: Optional[str] = None,
    niveau: Optional[str] = None,
    disponibles: Optional[str] = None,
    page: int = 1,
    session: Session = Depends(get_session),
):
    """Recherche nationale des cercles avec une hierarchie explicite.

    Identite affichee : Domaine -> Mention -> Parcours -> Niveau.
    La recherche textuelle couvre le nom, la description, la mention et
    le parcours au lieu de limiter le resultat au nom du cercle.
    """
    TAILLE_PAGE = 30
    utilisateur = utilisateur_courant(request, session)

    profil_academique_brut = None
    profil_academique_recherche = None
    if utilisateur and utilisateur.role in (RoleUtilisateur.ETUDIANT, RoleUtilisateur.PROFESSEUR):
        profil_academique_brut = referentiel_academique.contexte_profil_academique(utilisateur, session)
        profil_academique_recherche = referentiel_academique.serialiser_profil_academique(profil_academique_brut)

    q_nettoye = " ".join((q or "").split())[:160]

    # Les niveaux et le tronc commun sont des dimensions academiques,
    # pas de simples mots de titre. Les extraire ici permet a une requete
    # comme "gestion M1 CCA" de filtrer M1 tout en laissant la recherche
    # textuelle chercher "gestion" et "CCA" dans la hierarchie.
    niveaux_dans_q = []
    motifs_niveaux = (
        (r"\b(?:licence|l)\s*1\b", "L1"),
        (r"\b(?:licence|l)\s*2\b", "L2"),
        (r"\b(?:licence|l)\s*3\b", "L3"),
        (r"\b(?:master|m)\s*1\b", "M1"),
        (r"\b(?:master|m)\s*2\b", "M2"),
    )
    q_pour_recherche = q_nettoye
    for motif, valeur in motifs_niveaux:
        if re.search(motif, q_pour_recherche, flags=re.IGNORECASE):
            niveaux_dans_q.append(valeur)
            q_pour_recherche = re.sub(motif, " ", q_pour_recherche, flags=re.IGNORECASE)
    recherche_tronc_commun_dans_q = bool(
        re.search(r"\btronc\s+commun\b", q_pour_recherche, flags=re.IGNORECASE)
    )
    q_pour_recherche = re.sub(
        r"\btronc\s+commun\b", " ", q_pour_recherche, flags=re.IGNORECASE
    )
    q_pour_recherche = " ".join(q_pour_recherche.split())[:160]

    # Une requete composee de plusieurs mots doit rester utile meme si
    # l'utilisateur ne connait pas l'ordre exact du titre : chaque terme
    # doit apparaitre dans au moins un champ searchable. On borne a 6 termes
    # pour ne pas gonfler artificiellement la requete SQL.
    domaine_id_nettoye = entier_ou_none(domaine_id)
    mention_id_nettoye = entier_ou_none(mention_id)
    filiere_id_nettoye = entier_ou_none(filiere_id) if filiere_id != "tronc_commun" else None
    recherche_tronc_commun = filiere_id == "tronc_commun"
    niveau_nettoye = niveau if niveau in NIVEAUX else None

    # Cohérence stricte de la cascade : Parcours -> Mention -> Domaine.
    # Un paramètre incohérent ne doit jamais élargir les résultats.
    filiere_selectionnee = session.get(Filiere, filiere_id_nettoye) if filiere_id_nettoye else None
    if filiere_selectionnee:
        if (
            mention_id_nettoye
            and filiere_selectionnee.mention_id
            and mention_id_nettoye != filiere_selectionnee.mention_id
        ):
            filiere_id_nettoye = -1
            filiere_selectionnee = None
        elif filiere_selectionnee.mention_id:
            mention_id_nettoye = filiere_selectionnee.mention_id

    mention_selectionnee = session.get(Mention, mention_id_nettoye) if mention_id_nettoye else None
    if mention_selectionnee and mention_selectionnee.domaine_id:
        if domaine_id_nettoye and domaine_id_nettoye != mention_selectionnee.domaine_id:
            domaine_id_nettoye = -1
        elif not domaine_id_nettoye:
            domaine_id_nettoye = mention_selectionnee.domaine_id

    # Le tronc commun n'est défini que dans le contexte d'une mention.
    if recherche_tronc_commun and not mention_id_nettoye:
        recherche_tronc_commun = False
        recherche_tronc_commun_dans_q = False
        filiere_id_nettoye = -1
        niveau_nettoye = "__filtre_invalide__"

    afficher_disponibles_seulement = disponibles == "1"
    page_nettoyee = max(1, page)

    # Legacy compatibility : avant l'introduction de
    # CercleEtude.mention_id, certains cercles stockaient uniquement
    # filiere_id. La source de verite de la mention reste alors
    # Filiere.mention_id. On construit une "mention effective" pour que
    # la recherche Domaine -> Mention -> Niveau -> Parcours fonctionne
    # aussi sur ces cercles historiques.
    mention_effective_id = func.coalesce(CercleEtude.mention_id, Filiere.mention_id)

    requete = (
        select(CercleEtude)
        .outerjoin(Filiere, Filiere.id == CercleEtude.filiere_id)
        .outerjoin(Mention, Mention.id == mention_effective_id)
        .outerjoin(Domaine, Domaine.id == Mention.domaine_id)
        .where(CercleEtude.statut == StatutCercle.ACTIF)
        .where(or_(mention_effective_id.is_(None), Mention.est_active == True))  # noqa: E712
    )

    # Le texte searchable reprend toute la hierarchie de la base
    # Toamasina : Domaine -> Mention -> Niveau -> Parcours. Les cercles
    # de tronc commun sont representes sans Filiere, on leur ajoute donc
    # un tag de recherche explicite "tronc commun".
    referentiel_recherche = (
        func.coalesce(Domaine.nom, "")
        + " " + func.coalesce(Mention.nom, "")
        + " " + func.coalesce(CercleEtude.niveau, "")
        + " " + func.coalesce(Filiere.nom, "")
        + " "
        + func.coalesce(
            case(
                (CercleEtude.filiere_id.is_(None), "tronc commun"),
                else_="",
            ),
            "",
        )
    )
    condition_recherche, pertinence_recherche = clause_recherche_cercles(
        session,
        q_pour_recherche,
        CercleEtude.nom,
        CercleEtude.description,
        referentiel_recherche,
    )
    if condition_recherche is not None:
        requete = requete.where(condition_recherche)

    if niveaux_dans_q:
        requete = requete.where(
            CercleEtude.niveau.in_(sorted(set(niveaux_dans_q)))
        )

    if recherche_tronc_commun_dans_q:
        requete = requete.where(CercleEtude.filiere_id.is_(None))

    if domaine_id_nettoye:
        requete = requete.where(Mention.domaine_id == domaine_id_nettoye)

    if mention_id_nettoye:
        requete = requete.where(mention_effective_id == mention_id_nettoye)

    if recherche_tronc_commun:
        requete = requete.where(CercleEtude.filiere_id.is_(None))
    elif filiere_id_nettoye:
        filiere_choisie = session.get(Filiere, filiere_id_nettoye)
        if filiere_choisie:
            ids_equivalents = referentiel_academique._filieres_equivalentes(session, filiere_choisie)
            requete = requete.where(CercleEtude.filiere_id.in_(ids_equivalents))
        else:
            requete = requete.where(CercleEtude.id == -1)

    if niveau_nettoye:
        requete = requete.where(CercleEtude.niveau == niveau_nettoye)

    condition_disponibilite = None
    if afficher_disponibles_seulement and not _est_admin(utilisateur):
        # Construit une seule fois : la meme condition sert au filtre SQL et
        # au badge de compatibilite de la page, sans recalculer le profil.
        condition_disponibilite = referentiel_academique.condition_cercles_disponibles(
            utilisateur, session, profil=profil_academique_brut
        )
        requete = requete.where(condition_disponibilite)

    total_cercles = session.exec(
        select(func.count()).select_from(requete.subquery())
    ).one()
    total_pages = max(1, (total_cercles + TAILLE_PAGE - 1) // TAILLE_PAGE)
    page_nettoyee = min(page_nettoyee, total_pages)

    ordre = [CercleEtude.date_creation.desc(), CercleEtude.id.desc()]
    if pertinence_recherche is not None:
        ordre = [pertinence_recherche.desc()] + ordre

    cercles = session.exec(
        requete
        .order_by(*ordre)
        .offset((page_nettoyee - 1) * TAILLE_PAGE)
        .limit(TAILLE_PAGE)
    ).all()
    cercle_ids = [c.id for c in cercles]

    # Le formulaire suit la hierarchie nationale : Domaine -> Mention.
    domaines = session.exec(
        select(Domaine).where(Domaine.est_active == True).order_by(Domaine.nom)  # noqa: E712
    ).all()
    domaines_map = {d.id: d for d in domaines}
    mentions = session.exec(
        select(Mention).where(Mention.est_active == True).order_by(Mention.nom)  # noqa: E712
    ).all()

    filiere_ids = {c.filiere_id for c in cercles if c.filiere_id}
    filieres_map = {}
    if filiere_ids:
        filieres_map = {
            f.id: f for f in session.exec(select(Filiere).where(Filiere.id.in_(filiere_ids))).all()
        }
    mentions_map = {m.id: m for m in mentions}

    if _est_admin(utilisateur):
        cercles_ou_accessibles = set(cercle_ids)
    elif utilisateur and cercle_ids:
        cercles_ou_accessibles = {
            cid for cid in session.exec(
                select(MembreCercle.cercle_id).where(
                    MembreCercle.cercle_id.in_(cercle_ids),
                    MembreCercle.utilisateur_id == utilisateur.id,
                )
            ).all()
        }
    else:
        cercles_ou_accessibles = set()

    cercles_en_attente = set()
    if utilisateur and cercle_ids:
        cercles_en_attente = {
            cid for cid in session.exec(
                select(DemandeAdhesionCercle.cercle_id).where(
                    DemandeAdhesionCercle.cercle_id.in_(cercle_ids),
                    DemandeAdhesionCercle.utilisateur_id == utilisateur.id,
                    DemandeAdhesionCercle.statut == StatutDemandeAdhesion.EN_ATTENTE,
                )
            ).all()
        }

    compatibilites = set()
    if utilisateur and cercle_ids and not _est_admin(utilisateur):
        condition_compatibilite = (
            condition_disponibilite
            if condition_disponibilite is not None
            else referentiel_academique.condition_cercles_disponibles(
                utilisateur, session, profil=profil_academique_brut
            )
        )
        compatibilites = {
            cid for cid in session.exec(
                select(CercleEtude.id)
                .where(CercleEtude.id.in_(cercle_ids))
                .where(condition_compatibilite)
            ).all()
        }

    nb_membres_par_cercle = {}
    if cercle_ids:
        nb_membres_par_cercle = {
            cid: nb for cid, nb in session.exec(
                select(MembreCercle.cercle_id, func.count())
                .where(MembreCercle.cercle_id.in_(cercle_ids))
                .group_by(MembreCercle.cercle_id)
            ).all()
        }

    cercles_avec_info = []
    for cercle in cercles:
        filiere = filieres_map.get(cercle.filiere_id)
        mention_id_effectif = cercle.mention_id or (filiere.mention_id if filiere else None)
        mention = mentions_map.get(mention_id_effectif)
        domaine = domaines_map.get(mention.domaine_id) if mention and mention.domaine_id else None
        cercles_avec_info.append({
            "cercle": cercle,
            "type_cercle": referentiel_academique.type_cercle(cercle),
            "domaine": domaine,
            "mention": mention,
            "filiere": filiere,
            "nb_membres": nb_membres_par_cercle.get(cercle.id, 0),
            "est_membre": cercle.id in cercles_ou_accessibles,
            "en_attente": bool(utilisateur and cercle.id not in cercles_ou_accessibles and cercle.id in cercles_en_attente),
            "profil_compatible": cercle.id in compatibilites or bool(_est_admin(utilisateur)),
            "peut_gerer": _peut_gerer_cercle(cercle, utilisateur),
        })

    filiere_recherchee = session.get(Filiere, filiere_id_nettoye) if filiere_id_nettoye else None
    querystring = urlencode({
        k: v for k, v in {
            "q": q_nettoye,
            "domaine_id": domaine_id_nettoye,
            "mention_id": mention_id_nettoye,
            "filiere_id": "tronc_commun" if recherche_tronc_commun else filiere_id_nettoye,
            "niveau": niveau_nettoye,
            "disponibles": "1" if afficher_disponibles_seulement else None,
        }.items() if v not in (None, "")
    })

    return templates.TemplateResponse(
        request,
        "cercles_list.html",
        {
            "cercles_avec_info": cercles_avec_info,
            "domaines": domaines,
            "mentions": mentions,
            "filiere_recherchee": filiere_recherchee,
            "niveaux": NIVEAUX,
            "utilisateur": utilisateur,
            "theme_du_jour": theme_service.get_theme_du_jour(),
            "profil_academique_recherche": profil_academique_recherche,
            "recherche_q": q_nettoye,
            "recherche_domaine_id": domaine_id_nettoye,
            "recherche_mention_id": mention_id_nettoye,
            "recherche_filiere_id": filiere_id_nettoye,
            "recherche_tronc_commun": recherche_tronc_commun,
            "recherche_niveau": niveau_nettoye,
            "recherche_disponibles": afficher_disponibles_seulement,
            "page": page_nettoyee,
            "total_pages": total_pages,
            "total_cercles": total_cercles,
            "querystring": querystring,
        },
    )

@router.post("/cercles/creer")
def creer_cercle(
    request: Request,
    nom: str = Form(...),
    description: Optional[str] = Form(None),
    mention_id: Optional[str] = Form(None),
    filiere_id: Optional[str] = Form(None),
    niveau: Optional[str] = Form(None),
    raison: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Deux comportements distincts, selon ce qui est rempli :

    1) niveau fourni ET (filiere_id OU mention_id) -> c'est une demande
       de CERCLE NATIONAL (§20-27 du brief "cercles nationaux"). Pas de
       creation immediate : une DemandeCreationCercle EN_ATTENTE est
       creee, soumise a validation admin (voir approuver_demande_creation
       plus bas). La raison devient obligatoire dans ce cas. Depuis le
       11/09/2026 (Jake : "ameliorer la recherche/creation") :
       mention_id SEUL (sans filiere_id) demande un cercle de TRONC
       COMMUN -- mention+niveau, sans parcours precis -- jusque-la
       impossible a demander depuis ce formulaire.

    2) Sinon (filiere_id seul, ou aucun des deux = "groupe libre") ->
       comportement INCHANGE d'avant cette evolution : creation
       immediate, comme tous les cercles crees jusqu'ici. Rien ne
       casse pour l'usage existant."""
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    filiere_id_nettoye = entier_ou_none(filiere_id)
    mention_id_nettoye = entier_ou_none(mention_id)

    # LIMITE : max MAX_CERCLES_PAR_UTILISATEUR cercles crees par le meme
    # numero de telephone. On verrouille la ligne utilisateur
    # (SELECT ... FOR UPDATE) avant de compter, pour que deux creations
    # simultanees du meme compte ne puissent pas toutes les deux lire
    # "2 cercles existants" et passer ensemble sous la limite — la
    # deuxieme requete attend que la premiere ait commite avant de
    # recompter. Le COUNT porte directement sur CercleEtude (source de
    # verite = la base), jamais sur un compteur cache qui pourrait
    # diverger si un cercle est supprime ailleurs.
    session.exec(
        select(Utilisateur).where(Utilisateur.id == utilisateur.id).with_for_update()
    ).first()
    nb_cercles_existants = session.exec(
        select(func.count()).select_from(CercleEtude).where(CercleEtude.createur_id == utilisateur.id)
    ).one()
    if nb_cercles_existants >= MAX_CERCLES_PAR_UTILISATEUR:
        filieres = session.exec(select(Filiere)).all()
        cercles = session.exec(select(CercleEtude).order_by(CercleEtude.date_creation.desc())).all()
        cercle_ids = [c.id for c in cercles]
        nb_membres_par_cercle = {cid: nb for cid, nb in session.exec(
            select(MembreCercle.cercle_id, func.count())
            .where(MembreCercle.cercle_id.in_(cercle_ids or [-1]))
            .group_by(MembreCercle.cercle_id)
        ).all()}
        membres_utilisateur = {
            cid for cid in session.exec(
                select(MembreCercle.cercle_id).where(
                    MembreCercle.cercle_id.in_(cercle_ids or [-1]),
                    MembreCercle.utilisateur_id == utilisateur.id,
                )
            ).all()
        }
        cercles_avec_info = [{
            "cercle": c,
            "nb_membres": nb_membres_par_cercle.get(c.id, 0),
            "est_membre": c.id in membres_utilisateur,
            "en_attente": False,
            "peut_gerer": _peut_gerer_cercle(c, utilisateur),
        } for c in cercles]
        return templates.TemplateResponse(
            request,
            "cercles_list.html",
            {
                "cercles_avec_info": cercles_avec_info, "filieres": filieres, "niveaux": NIVEAUX, "utilisateur": utilisateur,
                "erreur": f"Vous avez deja atteint la limite de {MAX_CERCLES_PAR_UTILISATEUR} cercles crees.",
                "theme_du_jour": theme_service.get_theme_du_jour(),
                "recherche_q": "", "recherche_filiere_id": "", "recherche_niveau": "", "recherche_disponibles": False,
                "page": 1, "total_pages": 1, "total_cercles": len(cercles_avec_info),
            },
        )

    niveau_nettoye = (niveau or "").strip() or None

    # --- Cas 1 : demande de cercle NATIONAL (niveau + (filiere OU mention)) ---
    if niveau_nettoye and (filiere_id_nettoye or mention_id_nettoye):
        if niveau_nettoye not in NIVEAUX:
            return RedirectResponse("/cercles?erreur=niveau_invalide", status_code=303)

        filiere = None
        if filiere_id_nettoye:
            filiere = session.get(Filiere, filiere_id_nettoye)
            if not filiere:
                return RedirectResponse("/cercles?erreur=filiere_introuvable", status_code=303)
            if not filiere.mention_id:
                # §10 du brief : la coherence mention/filiere doit etre
                # verifiee avant tout. Une filiere sans mention assignee ne
                # peut pas encore porter de cercle national (voir
                # /admin/referentiel pour l'assigner).
                return RedirectResponse("/cercles?erreur=filiere_sans_mention", status_code=303)
            mention_id_cible = filiere.mention_id
        else:
            # Tronc commun (11/09/2026) : mention seule, aucun parcours
            # precis -- voir le rapport du 10/09/2026 sur Filiere.niveau.
            mention = session.get(Mention, mention_id_nettoye)
            if not mention:
                return RedirectResponse("/cercles?erreur=mention_introuvable", status_code=303)
            mention_id_cible = mention.id

        raison_nettoyee = (raison or "").strip()
        if not raison_nettoyee:
            return RedirectResponse("/cercles?erreur=raison_requise", status_code=303)

        # §48 : si le cercle national existe deja, ne pas proposer de
        # doublon — rediriger vers l'existant.
        if filiere:
            filieres_equivalentes = referentiel_academique._filieres_equivalentes(session, filiere)
        else:
            filieres_equivalentes = []

        cercle_existant_requete = select(CercleEtude).where(
            CercleEtude.mention_id == mention_id_cible,
            CercleEtude.niveau == niveau_nettoye,
            CercleEtude.statut == StatutCercle.ACTIF,
        )
        if filiere:
            cercle_existant_requete = cercle_existant_requete.where(
                CercleEtude.filiere_id.in_(filieres_equivalentes)
            )
        else:
            cercle_existant_requete = cercle_existant_requete.where(CercleEtude.filiere_id.is_(None))

        cercle_existant = session.exec(cercle_existant_requete).first()
        if cercle_existant:
            return RedirectResponse(f"/cercles/{cercle_existant.id}?erreur=cercle_existe_deja", status_code=303)

        # Evite d'empiler plusieurs demandes EN_ATTENTE identiques (pas
        # une contrainte base de donnees ici — juste une verification
        # applicative, le vrai garde-fou contre les cercles en double
        # reste l'index unique sur CercleEtude, verifie a nouveau au
        # moment de l'approbation).
        demande_existante_requete = select(DemandeCreationCercle).where(
            DemandeCreationCercle.mention_id == mention_id_cible,
            DemandeCreationCercle.niveau == niveau_nettoye,
            DemandeCreationCercle.statut == StatutDemandeCreationCercle.EN_ATTENTE,
        )
        if filiere:
            demande_existante_requete = demande_existante_requete.where(
                DemandeCreationCercle.filiere_id.in_(filieres_equivalentes)
            )
        else:
            demande_existante_requete = demande_existante_requete.where(
                DemandeCreationCercle.filiere_id.is_(None)
            )
        demande_existante = session.exec(demande_existante_requete).first()
        if demande_existante:
            return RedirectResponse("/cercles?erreur=demande_deja_en_attente", status_code=303)

        session.add(DemandeCreationCercle(
            utilisateur_id=utilisateur.id,
            mention_id=mention_id_cible,
            filiere_id=filiere_id_nettoye,
            niveau=niveau_nettoye,
            nom=nom,
            description=description or None,
            raison=raison_nettoyee,
        ))
        session.commit()
        return RedirectResponse("/cercles?ok=demande_creation_envoyee", status_code=303)

    # --- Cas 2 : cercle "libre" (filiere seule ou aucune) — comportement inchange ---
    cercle = CercleEtude(
        nom=nom,
        description=description or None,
        filiere_id=filiere_id_nettoye,
        createur_id=utilisateur.id,
    )
    session.add(cercle)
    session.commit()
    session.refresh(cercle)

    # Le createur rejoint automatiquement son propre cercle.
    session.add(MembreCercle(
        cercle_id=cercle.id,
        utilisateur_id=utilisateur.id,
        role=RoleMembreCercle.CREATEUR,
    ))
    session.commit()

    return RedirectResponse(f"/cercles/{cercle.id}", status_code=303)


@router.post("/cercles/{cercle_id}/demander")
def demander_adhesion(
    request: Request,
    cercle_id: int,
    raison: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Deux chemins bien distincts, corrige suite a un retour de Jake :

    1) Le cercle national correspond EXACTEMENT au profil de l'etudiant
       (meme mention/parcours/niveau, via profil_correspond_au_cercle) :
       adhesion IMMEDIATE, sans demande ni raison a fournir — c'est son
       cercle par construction (le referentiel academique l'a deja
       determine a l'inscription/l'approbation de sa filiere), lui faire
       en plus attendre une validation manuelle n'aurait aucun sens et
       ne faisait que dupliquer un controle deja fait ailleurs.

    2) N'importe quel autre cercle (nationale mais qui ne correspond
       pas a son profil, OU cercle "libre") : reste soumis a une
       DemandeAdhesionCercle EN_ATTENTE avec raison obligatoire, validee
       par le createur/un admin — AVANT ce correctif, un cercle national
       non-correspondant etait purement et simplement BLOQUE (aucune
       demande possible) ; c'est desormais une vraie demande, pas un mur.
    """
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle or cercle.statut != StatutCercle.ACTIF:
        return RedirectResponse("/cercles", status_code=303)

    # Defense en profondeur : meme si l'interface ne devrait jamais
    # proposer ce bouton a un Admin (voir liste_cercles/salon_cercle qui
    # l'assurent deja membre en amont), un appel direct sur cette route
    # (POST forge, ancienne page en cache, etc.) ne doit jamais faire
    # passer un Admin par le circuit de demande — il est rendu membre
    # immediatement, sans creation de DemandeAdhesionCercle.
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    if _a_acces_cercle(session, cercle_id, utilisateur.id):
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    if referentiel_academique.profil_correspond_au_cercle(utilisateur, cercle, session):
        # Chemin 1 : son propre cercle national -> adhesion immediate.
        session.add(MembreCercle(cercle_id=cercle_id, utilisateur_id=utilisateur.id, role=RoleMembreCercle.MEMBRE))
        session.commit()
        return RedirectResponse(f"/cercles/{cercle_id}?ok=rejoint", status_code=303)

    # Chemin 2 : cercle qui n'est pas le sien (autre mention/filiere/
    # niveau, ou cercle libre) -> demande soumise a validation, raison
    # obligatoire pour que le createur/admin comprenne la requete.
    raison_nettoyee = (raison or "").strip()
    if not raison_nettoyee:
        return RedirectResponse(f"/cercles/{cercle_id}?erreur=raison_requise", status_code=303)

    # Empeche le doublon cote applicatif (verification rapide, UX claire) ;
    # l'index unique partiel en base (migration c4e91a2f7b6d) est le vrai
    # garde-fou en cas de requetes concurrentes.
    if not _demande_en_attente(session, cercle_id, utilisateur.id):
        session.add(DemandeAdhesionCercle(cercle_id=cercle_id, utilisateur_id=utilisateur.id, raison=raison_nettoyee))
        session.commit()

    return RedirectResponse("/cercles", status_code=303)


@router.get("/cercles/{cercle_id}/membres")
def voir_membres(request: Request, cercle_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle or cercle.statut != StatutCercle.ACTIF:
        return RedirectResponse("/cercles", status_code=303)


    # Seuls les membres du cercle (+ createur/admin, qui sont de toute
    # facon membres ou geres a part) peuvent voir la liste — un visiteur
    # externe non-membre n'a pas a voir qui est dans le cercle.
    if not _a_acces_cercle(session, cercle_id, utilisateur.id) and not _peut_gerer_cercle(cercle, utilisateur):
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    lignes = session.exec(
        select(MembreCercle, Utilisateur)
        .where(MembreCercle.cercle_id == cercle_id)
        .where(MembreCercle.utilisateur_id == Utilisateur.id)
        .order_by(MembreCercle.date_adhesion)
    ).all()
    membres = [{"membre": m, "utilisateur": u} for m, u in lignes]

    return templates.TemplateResponse(
        request,
        "cercle_membres.html",
        {
            "utilisateur": utilisateur,
            "cercle": cercle,
            "membres": membres,
            "peut_gerer": _peut_gerer_cercle(cercle, utilisateur),
        },
    )


@router.post("/cercles/{cercle_id}/membres/ajouter")
def ajouter_membre_par_telephone(
    request: Request,
    cercle_id: int,
    telephone: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Ajout direct d'un membre par numero de telephone, sans passer par
    le workflow de demande — reserve au createur du cercle (le sien
    uniquement) ou a un admin. L'utilisateur cible doit deja avoir un
    compte Gasy Mahay (on ne cree pas de compte a sa place)."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle or cercle.statut != StatutCercle.ACTIF:
        return RedirectResponse("/cercles", status_code=303)

    if not _peut_gerer_cercle(cercle, utilisateur):
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    cible = session.exec(select(Utilisateur).where(Utilisateur.telephone == telephone.strip())).first()
    if not cible:
        return RedirectResponse(f"/cercles/{cercle_id}/membres?erreur=utilisateur_introuvable", status_code=303)

    if referentiel_academique.cercle_est_national(cercle):
        if not referentiel_academique.profil_correspond_au_cercle(cible, cercle, session):
            return RedirectResponse(
                f"/cercles/{cercle_id}/membres?erreur=profil_incompatible",
                status_code=303,
            )

    if not _a_acces_cercle(session, cercle_id, cible.id):
        session.add(MembreCercle(
            cercle_id=cercle_id,
            utilisateur_id=cible.id,
            role=RoleMembreCercle.MEMBRE,
        ))
        session.commit()

    return RedirectResponse(f"/cercles/{cercle_id}/membres?ajoute=1", status_code=303)


@router.get("/cercles/{cercle_id}/demandes")
def voir_demandes(request: Request, cercle_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle or cercle.statut != StatutCercle.ACTIF:
        return RedirectResponse("/cercles", status_code=303)

    if not _peut_gerer_cercle(cercle, utilisateur):
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    lignes = session.exec(
        select(DemandeAdhesionCercle, Utilisateur)
        .where(DemandeAdhesionCercle.cercle_id == cercle_id)
        .where(DemandeAdhesionCercle.statut == StatutDemandeAdhesion.EN_ATTENTE)
        .where(DemandeAdhesionCercle.utilisateur_id == Utilisateur.id)
        .order_by(DemandeAdhesionCercle.date_creation)
    ).all()
    demandes = [{"demande": d, "utilisateur": u} for d, u in lignes]

    return templates.TemplateResponse(
        request,
        "cercle_demandes.html",
        {"utilisateur": utilisateur, "cercle": cercle, "demandes": demandes},
    )


def _traiter_acceptation_demande(session: Session, cercle: CercleEtude, demande: DemandeAdhesionCercle, traiteur: Utilisateur) -> Optional[str]:
    """Logique d'acceptation d'une DemandeAdhesionCercle, partagee entre
    la page de gestion du cercle (createur/admin, cercles_router.py) et
    la liste globale admin (/admin/demandes-adhesion, admin_router.py) —
    evite de dupliquer la reverification de profil ci-dessous dans les
    deux endroits.

    Retourne :
    - None si la demande a ete acceptee (membre ajoute) ;
    - "profil_change" si elle a ete rejetee a la place car le profil du
      demandeur ne correspond plus au cercle (voir §32 du brief) ;
    - "deja_traitee" si elle n'etait plus EN_ATTENTE (double-clic / action
      concurrente) — ne fait rien dans ce cas.
    """
    if demande.statut != StatutDemandeAdhesion.EN_ATTENTE:
        return "deja_traitee"

    demandeur = session.get(Utilisateur, demande.utilisateur_id)
    # §32 du brief : le niveau (ou la filiere) du demandeur a pu changer
    # entre la demande et son traitement — la verification doit etre
    # refaite ICI, pas seulement au moment de la demande. Si ca ne
    # correspond plus, on refuse au lieu d'accepter silencieusement dans
    # le mauvais cercle.
    if demandeur and not referentiel_academique.profil_correspond_au_cercle(demandeur, cercle, session):
        demande.statut = StatutDemandeAdhesion.REJETEE
        demande.date_traitement = datetime.utcnow()
        demande.traite_par_id = traiteur.id
        session.add(demande)
        session.commit()
        return "profil_change"

    demande.statut = StatutDemandeAdhesion.ACCEPTEE
    demande.date_traitement = datetime.utcnow()
    demande.traite_par_id = traiteur.id
    session.add(demande)
    if not _a_acces_cercle(session, cercle.id, demande.utilisateur_id):
        session.add(MembreCercle(cercle_id=cercle.id, utilisateur_id=demande.utilisateur_id))
    session.commit()
    return None


def _traiter_refus_demande(session: Session, demande: DemandeAdhesionCercle, traiteur: Utilisateur) -> None:
    """Logique de refus d'une DemandeAdhesionCercle, partagee avec la
    liste globale admin — voir _traiter_acceptation_demande ci-dessus."""
    if demande.statut == StatutDemandeAdhesion.EN_ATTENTE:
        demande.statut = StatutDemandeAdhesion.REJETEE
        demande.date_traitement = datetime.utcnow()
        demande.traite_par_id = traiteur.id
        session.add(demande)
        session.commit()


@router.post("/cercles/{cercle_id}/demandes/{demande_id}/accepter")
def accepter_demande(request: Request, cercle_id: int, demande_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cercle = session.get(CercleEtude, cercle_id)
    demande = session.get(DemandeAdhesionCercle, demande_id)
    if not cercle or not demande or demande.cercle_id != cercle_id:
        return RedirectResponse("/cercles", status_code=303)

    if not _peut_gerer_cercle(cercle, utilisateur):
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    resultat = _traiter_acceptation_demande(session, cercle, demande, utilisateur)
    if resultat == "profil_change":
        return RedirectResponse(f"/cercles/{cercle_id}/demandes?erreur=profil_change", status_code=303)

    return RedirectResponse(f"/cercles/{cercle_id}/demandes", status_code=303)


@router.post("/cercles/{cercle_id}/demandes/{demande_id}/refuser")
def refuser_demande(request: Request, cercle_id: int, demande_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cercle = session.get(CercleEtude, cercle_id)
    demande = session.get(DemandeAdhesionCercle, demande_id)
    if not cercle or not demande or demande.cercle_id != cercle_id:
        return RedirectResponse("/cercles", status_code=303)

    if not _peut_gerer_cercle(cercle, utilisateur):
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    _traiter_refus_demande(session, demande, utilisateur)

    return RedirectResponse(f"/cercles/{cercle_id}/demandes", status_code=303)


@router.post("/cercles/{cercle_id}/quitter")
def quitter_cercle(request: Request, cercle_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle or cercle.statut != StatutCercle.ACTIF:
        return RedirectResponse("/cercles", status_code=303)

    # Le createur ne peut pas "quitter" comme un membre normal : il doit
    # soit supprimer le cercle, soit (fonctionnalite future) transferer
    # la propriete. Sans ca, un cercle se retrouverait sans proprietaire.
    if utilisateur.id == cercle.createur_id:
        return RedirectResponse(f"/cercles/{cercle_id}?erreur=createur_ne_peut_quitter", status_code=303)

    membre = session.exec(
        select(MembreCercle).where(
            MembreCercle.cercle_id == cercle_id,
            MembreCercle.utilisateur_id == utilisateur.id,
        )
    ).first()
    if membre:
        session.delete(membre)
        session.commit()

    return RedirectResponse("/cercles", status_code=303)


@router.post("/cercles/{cercle_id}/membres/{utilisateur_id}/retirer")
def retirer_membre(request: Request, cercle_id: int, utilisateur_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle or cercle.statut != StatutCercle.ACTIF:
        return RedirectResponse("/cercles", status_code=303)

    if not _peut_gerer_cercle(cercle, utilisateur):
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    # Le createur ne se retire pas lui-meme via cette route (il devrait
    # supprimer le cercle a la place) — evite un cercle sans proprietaire.
    if utilisateur_id == cercle.createur_id:
        return RedirectResponse(f"/cercles/{cercle_id}/membres?erreur=impossible_retirer_createur", status_code=303)

    # Hierarchie ADMIN_GLOBAL > OWNER : meme le createur/proprietaire du
    # cercle ne peut jamais retirer un administrateur global de son
    # espace. Un compte admin ne se gere qu'au niveau plateforme (voir
    # admin_router.py), jamais depuis un cercle particulier.
    cible = session.get(Utilisateur, utilisateur_id)
    if cible and cible.role == RoleUtilisateur.ADMIN:
        return RedirectResponse(f"/cercles/{cercle_id}/membres?erreur=impossible_retirer_admin", status_code=303)

    membre = session.exec(
        select(MembreCercle).where(
            MembreCercle.cercle_id == cercle_id,
            MembreCercle.utilisateur_id == utilisateur_id,
        )
    ).first()
    if membre:
        session.delete(membre)
        session.commit()

    return RedirectResponse(f"/cercles/{cercle_id}/membres", status_code=303)


@router.post("/cercles/{cercle_id}/supprimer")
def supprimer_cercle(request: Request, cercle_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle or cercle.statut != StatutCercle.ACTIF:
        return RedirectResponse("/cercles", status_code=303)

    if not _peut_gerer_cercle(cercle, utilisateur):
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    _supprimer_cercle_et_contenu(session, cercle_id)
    session.commit()

    return RedirectResponse("/cercles?supprime=1", status_code=303)


@router.get("/cercles/{cercle_id}")
def salon_cercle(request: Request, cercle_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle or cercle.statut != StatutCercle.ACTIF:
        return RedirectResponse("/cercles", status_code=303)

    # Filet de securite pour les cercles crees AVANT cette regle (ou si un
    # nouvel admin a ete cree apres coup) : garantit que l'admin courant a
    # bien une adhesion reelle avant qu'on calcule `membre` juste apres.

    membre = _a_acces_cercle(session, cercle_id, utilisateur.id)
    en_attente = bool(not membre and _demande_en_attente(session, cercle_id, utilisateur.id))

    messages = []
    message_epingle = None
    membres_pour_mentions = []
    if membre:
        membres_pour_mentions = [
            {"id": u2.id, "nom": u2.nom}
            for u2 in session.exec(
                select(Utilisateur)
                .join(MembreCercle, MembreCercle.utilisateur_id == Utilisateur.id)
                .where(MembreCercle.cercle_id == cercle_id)
                .where(Utilisateur.id != utilisateur.id)
            ).all()
        ]
        lignes = session.exec(
            select(MessageCercle, Utilisateur)
            .where(MessageCercle.cercle_id == cercle_id)
            .where(MessageCercle.auteur_id == Utilisateur.id)
            .where(MessageCercle.supprime == False)  # noqa: E712 — comparaison SQLModel/SQLAlchemy, pas Python
            # Seul le fil principal est charge ici : les reponses
            # (parent_message_id renseigne) sont chargees a la demande par
            # /cercles/{id}/messages/{id}/thread quand l'utilisateur ouvre
            # le panneau (§28 : chargement progressif des threads).
            .where(MessageCercle.parent_message_id == None)  # noqa: E711
            .order_by(MessageCercle.date_envoi)
        ).all()
        auteurs_epinglage_ids = {m.epingle_par_id for m, _ in lignes if m.epingle_par_id}
        noms_epingleurs = {
            u2.id: u2.nom
            for u2 in session.exec(select(Utilisateur).where(Utilisateur.id.in_(auteurs_epinglage_ids))).all()
        } if auteurs_epinglage_ids else {}

        message_ids = [m.id for m, _u in lignes]
        nb_reponses_par_message = {mid: nb for mid, nb in session.exec(
            select(MessageCercle.parent_message_id, func.count())
            .where(
                MessageCercle.parent_message_id.in_(message_ids or [-1]),
                MessageCercle.supprime == False,  # noqa: E712
            )
            .group_by(MessageCercle.parent_message_id)
        ).all()}
        reponses = session.exec(
            select(MessageCercle, Utilisateur)
            .where(
                MessageCercle.parent_message_id.in_(message_ids or [-1]),
                MessageCercle.supprime == False,  # noqa: E712
            )
            .where(MessageCercle.auteur_id == Utilisateur.id)
        ).all()
        derniere_reponse_par_message = {}
        for reponse, auteur_reponse in reponses:
            courante = derniere_reponse_par_message.get(reponse.parent_message_id)
            if courante is None or reponse.date_envoi > courante[0].date_envoi:
                contenu = reponse.piece_jointe_nom if reponse.piece_jointe_chemin else (reponse.contenu or "")
                derniere_reponse_par_message[reponse.parent_message_id] = (
                    reponse, auteur_reponse,
                    contenu[:79].rstrip() + "…" if len(contenu) > 80 else contenu,
                )

        reactions_lignes = session.exec(
            select(MessageReaction).where(MessageReaction.message_id.in_(message_ids or [-1]))
        ).all()
        reactions_par_message = {}
        for reaction in reactions_lignes:
            par_type = reactions_par_message.setdefault(reaction.message_id, {})
            entree = par_type.setdefault(reaction.type_reaction.value, {
                "type_reaction": reaction.type_reaction.value, "total": 0, "mienne": False
            })
            entree["total"] += 1
            if reaction.utilisateur_id == utilisateur.id:
                entree["mienne"] = True

        messages = []
        for m, u in lignes:
            nb_reponses = nb_reponses_par_message.get(m.id, 0)
            derniere = derniere_reponse_par_message.get(m.id)
            dernier_apercu = (
                {"auteur": derniere[1].nom, "contenu": derniere[2]}
                if derniere else None
            )
            groupes = reactions_par_message.get(m.id, {})
            reactions = [groupes[t.value] for t in TypeReaction if t.value in groupes]
            messages.append({
                "id": m.id,
                "auteur": u.nom,
                "auteur_id": u.id,
                "auteur_a_une_photo": bool(u.photo_chemin),
                "contenu": m.contenu,
                "piece_jointe_chemin": m.piece_jointe_chemin,
                "piece_jointe_nom": m.piece_jointe_nom,
                "est_moi": u.id == utilisateur.id,
                "date_envoi": m.date_envoi,
                "modifie": m.date_modification is not None,
                "epingle": m.epingle,
                "reponses": nb_reponses,
                "derniere_reponse": dernier_apercu,
                "reactions": reactions,
            })
        ligne_epinglee = next((m for m, _ in lignes if m.epingle), None)
        if ligne_epinglee:
            message_epingle = {
                "id": ligne_epinglee.id,
                "contenu": ligne_epinglee.contenu,
                "epingle_par": noms_epingleurs.get(ligne_epinglee.epingle_par_id),
            }

    return templates.TemplateResponse(
        request,
        "cercle_chat.html",
        {
            "cercle": cercle,
            "membre": membre,
            "en_attente": en_attente,
            "profil_compatible": referentiel_academique.profil_correspond_au_cercle(utilisateur, cercle, session),
            "cercle_est_national": referentiel_academique.cercle_est_national(cercle),
            "peut_gerer": _peut_gerer_cercle(cercle, utilisateur),
            "messages": messages,
            "message_epingle": message_epingle,
            "membres_pour_mentions": membres_pour_mentions,
            "utilisateur": utilisateur,
        },
    )


@router.post("/cercles/{cercle_id}/message-fichier")
async def envoyer_fichier(
    request: Request,
    cercle_id: int,
    fichier: UploadFile = File(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Partage d'un PDF dans le salon. Passe par une route HTTP classique
    (pas le WebSocket) car un upload de fichier binaire ne s'y prete pas
    bien ; le message resultant est ensuite diffuse en temps reel aux
    membres connectes exactement comme un message texte."""
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle or cercle.statut != StatutCercle.ACTIF:
        return RedirectResponse("/cercles", status_code=303)

    if not _a_acces_cercle(session, cercle_id, utilisateur.id):
        return RedirectResponse("/cercles", status_code=303)

    if not fichier.filename or not fichier.filename.lower().endswith(".pdf"):
        return RedirectResponse(f"/cercles/{cercle_id}?erreur=pdf_uniquement", status_code=303)

    # Verifie la taille avant meme d'appeler sauvegarder_fichier() : cette
    # constante existait deja mais n'etait jusqu'ici jamais appliquee nulle
    # part, ce qui laissait n'importe quelle taille de PDF passer. seek/tell
    # mesure sans consommer le flux (on revient au debut juste apres).
    fichier.file.seek(0, 2)  # 2 = SEEK_END
    taille = fichier.file.tell()
    fichier.file.seek(0)
    if taille > TAILLE_MAX_PIECE_JOINTE:
        return RedirectResponse(f"/cercles/{cercle_id}?erreur=fichier_trop_volumineux", status_code=303)

    reference = f"cercle_{cercle_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    # sauvegarder_fichier() revalide aussi independamment le type/la taille
    # (voir app/storage.py) — double protection si jamais cette route
    # evoluait un jour pour accepter d'autres extensions que .pdf.
    try:
        chemin_stocke = sauvegarder_fichier(fichier, reference)
    except FichierInvalide:
        return RedirectResponse(f"/cercles/{cercle_id}?erreur=pdf_uniquement", status_code=303)

    message = MessageCercle(
        cercle_id=cercle_id,
        auteur_id=utilisateur.id,
        contenu="",
        piece_jointe_chemin=chemin_stocke,
        piece_jointe_nom=fichier.filename,
    )
    session.add(message)
    session.commit()
    session.refresh(message)

    await gestionnaire.diffuser(cercle_id, {
        "type": "message",
        "id": message.id,
        "auteur": utilisateur.nom,
        "auteur_id": utilisateur.id,
        "auteur_a_une_photo": bool(utilisateur.photo_chemin),
        "contenu": "",
        "piece_jointe_nom": fichier.filename,
        "piece_jointe_url": f"/cercles/{cercle_id}/messages/{message.id}/piece-jointe",
        "date_envoi": message.date_envoi.isoformat(),
    })

    return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)


@router.get("/cercles/{cercle_id}/messages/{message_id}/piece-jointe")
def telecharger_piece_jointe(request: Request, cercle_id: int, message_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    if not _a_acces_cercle(session, cercle_id, utilisateur.id):
        return RedirectResponse("/connexion", status_code=303)

    message = session.get(MessageCercle, message_id)
    if not message or message.cercle_id != cercle_id or not message.piece_jointe_chemin or message.supprime:
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    if stockage_distant_actif():
        return RedirectResponse(obtenir_url_telechargement(message.piece_jointe_chemin))
    return FileResponse(message.piece_jointe_chemin, filename=message.piece_jointe_nom or "document.pdf")


@router.post("/cercles/{cercle_id}/messages/{message_id}/supprimer")
async def supprimer_message(request: Request, cercle_id: int, message_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    """Suppression d'un message par son propre auteur uniquement.

    Regle stricte et non contournable : un utilisateur ne peut jamais
    supprimer un message envoye par quelqu'un d'autre, meme s'il est
    createur du cercle. La moderation par un administrateur passe par un
    circuit distinct et explicitement protege : voir
    /admin/moderation-salon (app/routers/admin_router.py), qui agit sur
    signalement et verifie le role admin separement."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle or cercle.statut != StatutCercle.ACTIF:
        return RedirectResponse("/cercles", status_code=303)

    message = session.get(MessageCercle, message_id)
    if not cercle or not message or message.cercle_id != cercle_id:
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    if message.auteur_id != utilisateur.id:
        # Tentative de suppression du message d'un autre utilisateur :
        # refusee sans exception, y compris pour le createur du cercle.
        return RedirectResponse(f"/cercles/{cercle_id}?erreur=suppression_refusee", status_code=303)

    message.supprime = True
    session.add(message)
    session.commit()

    await gestionnaire.diffuser(cercle_id, {"type": "suppression", "id": message.id})

    return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)


@router.post("/cercles/{cercle_id}/messages/{message_id}/signaler")
def signaler_message(
    request: Request,
    cercle_id: int,
    message_id: int,
    motif: str = Form(...),
    motif_autre: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Signalement d'un message par un membre du cercle.

    Deux regles imperatives, verifiees cote serveur (l'interface les
    applique deja, mais ne suffit pas seule a les garantir) :
    - un utilisateur ne peut pas signaler son propre message ;
    - un motif non vide est obligatoire (choisi dans la liste, ou saisi
      librement si "Autre" est selectionne)."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    message = session.get(MessageCercle, message_id)
    if not message or message.cercle_id != cercle_id or not _a_acces_cercle(session, cercle_id, utilisateur.id):
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    if message.auteur_id == utilisateur.id:
        # On ne peut pas signaler son propre message, meme via un POST
        # direct qui contournerait l'interface (qui masque deja le bouton).
        return RedirectResponse(f"/cercles/{cercle_id}?erreur=signalement_refuse", status_code=303)

    motif_choisi = (motif or "").strip()
    if motif_choisi not in MOTIFS_SIGNALEMENT_AUTORISES:
        return RedirectResponse(f"/cercles/{cercle_id}?erreur=motif_requis", status_code=303)

    motif_final = motif_choisi
    if motif_choisi == "Autre":
        motif_final = (motif_autre or "").strip()

    if not motif_final:
        # Motif obligatoire : vide (y compris "Autre" laisse sans
        # precision) est rejete, on ne cree aucun signalement muet.
        return RedirectResponse(f"/cercles/{cercle_id}?erreur=motif_requis", status_code=303)

    # Evite les doublons : un signalement non-traite deja existant de ce
    # meme utilisateur sur ce meme message n'est pas duplique.
    deja_signale = session.exec(
        select(SignalementMessage).where(
            SignalementMessage.message_id == message_id,
            SignalementMessage.signale_par_id == utilisateur.id,
            SignalementMessage.traite == False,  # noqa: E712
        )
    ).first()
    if not deja_signale:
        session.add(SignalementMessage(message_id=message_id, signale_par_id=utilisateur.id, motif=motif_final))
        session.commit()

    return RedirectResponse(f"/cercles/{cercle_id}?signale=1", status_code=303)


@router.post("/cercles/{cercle_id}/messages/{message_id}/reaction")
async def reagir_message(
    request: Request,
    cercle_id: int,
    message_id: int,
    type_reaction: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Ajoute/retire/change la reaction de l'utilisateur courant sur un
    message (§4 du brief). Comportement "WhatsApp-style" : un utilisateur
    n'a jamais plus d'UNE reaction active a la fois sur un meme message.
    - meme emoji que la reaction actuelle -> on la retire ;
    - emoji different -> on remplace l'ancienne par la nouvelle ;
    - pas de reaction actuelle -> on l'ajoute.
    Repond en JSON (pas de redirection) : appele en AJAX depuis le chat
    pour eviter un rechargement complet de la page a chaque clic (§28).
    """
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        raise HTTPException(status_code=401, detail="Non connecte.")

    try:
        type_valide = TypeReaction(type_reaction)
    except ValueError:
        raise HTTPException(status_code=400, detail="Type de reaction invalide.")

    message = session.get(MessageCercle, message_id)
    if not message or message.cercle_id != cercle_id or message.supprime:
        raise HTTPException(status_code=404, detail="Message introuvable.")
    if not _a_acces_cercle(session, cercle_id, utilisateur.id):
        raise HTTPException(status_code=403, detail="Vous n'etes pas membre de ce cercle.")

    reaction_existante = session.exec(
        select(MessageReaction).where(
            MessageReaction.message_id == message_id,
            MessageReaction.utilisateur_id == utilisateur.id,
        )
    ).first()

    if reaction_existante and reaction_existante.type_reaction == type_valide:
        session.delete(reaction_existante)
        session.commit()
    else:
        if reaction_existante:
            session.delete(reaction_existante)
            session.commit()
        session.add(MessageReaction(message_id=message_id, utilisateur_id=utilisateur.id, type_reaction=type_valide))
        session.commit()
        if message.auteur_id != utilisateur.id:
            _creer_notification(
                session,
                destinataire_id=message.auteur_id,
                type_notification=TypeNotification.REACTION,
                contenu=f"{utilisateur.nom} a reagi {type_valide.value} a votre message",
                acteur_id=utilisateur.id,
                cercle_id=cercle_id,
                message_id=message_id,
            )

    reactions = _reactions_du_message(session, message_id, utilisateur.id)
    await gestionnaire.diffuser(cercle_id, {"type": "reaction", "message_id": message_id, "reactions": reactions})
    return {"reactions": reactions}


@router.post("/cercles/{cercle_id}/messages/{message_id}/modifier")
async def modifier_message(
    request: Request,
    cercle_id: int,
    message_id: int,
    contenu: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Modification du contenu d'un message par son auteur uniquement
    (§9 du brief). Meme regle stricte que la suppression : personne
    d'autre, y compris le createur du cercle ou un admin, ne peut
    modifier le message de quelqu'un d'autre — seule la suppression via
    signalement/moderation admin existe pour le contenu d'autrui."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        raise HTTPException(status_code=401, detail="Non connecte.")

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle or cercle.statut != StatutCercle.ACTIF:
        raise HTTPException(status_code=404, detail="Cercle introuvable.")

    message = session.get(MessageCercle, message_id)
    if not message or message.cercle_id != cercle_id or message.supprime:
        raise HTTPException(status_code=404, detail="Message introuvable.")
    if message.auteur_id != utilisateur.id:
        raise HTTPException(status_code=403, detail="Vous ne pouvez modifier que vos propres messages.")

    contenu_nettoye = contenu.strip()[:LONGUEUR_MAX_MESSAGE]
    if not contenu_nettoye:
        raise HTTPException(status_code=400, detail="Le message ne peut pas etre vide.")

    message.contenu = contenu_nettoye
    message.date_modification = datetime.utcnow()
    session.add(message)
    session.commit()

    await gestionnaire.diffuser(cercle_id, {
        "type": "message_modifie",
        "id": message.id,
        "contenu": contenu_nettoye,
    })
    return {"id": message.id, "contenu": contenu_nettoye}


@router.post("/cercles/{cercle_id}/messages/{message_id}/epingler")
async def epingler_message(
    request: Request,
    cercle_id: int,
    message_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Epingle un message (§10). Reserve aux personnes qui peuvent gerer
    le cercle (createur ou admin — meme regle que _peut_gerer_cercle,
    utilisee partout ailleurs pour les actions de moderation du cercle).
    Un seul message epingle a la fois : en epingler un nouveau desepingle
    automatiquement l'ancien."""
    utilisateur = utilisateur_courant(request, session)
    cercle = session.get(CercleEtude, cercle_id)
    if not utilisateur or not cercle:
        raise HTTPException(status_code=404, detail="Cercle introuvable.")
    if not _peut_gerer_cercle(cercle, utilisateur):
        raise HTTPException(status_code=403, detail="Action reservee au createur du cercle ou a un administrateur.")

    message = session.get(MessageCercle, message_id)
    if not message or message.cercle_id != cercle_id or message.supprime:
        raise HTTPException(status_code=404, detail="Message introuvable.")

    anciens_epingles = session.exec(
        select(MessageCercle).where(MessageCercle.cercle_id == cercle_id, MessageCercle.epingle == True)  # noqa: E712
    ).all()
    for ancien in anciens_epingles:
        ancien.epingle = False
        ancien.epingle_par_id = None
        ancien.date_epinglage = None
        session.add(ancien)

    message.epingle = True
    message.epingle_par_id = utilisateur.id
    message.date_epinglage = datetime.utcnow()
    session.add(message)
    session.commit()

    await gestionnaire.diffuser(cercle_id, {
        "type": "epinglage",
        "id": message.id,
        "contenu": message.contenu,
        "epingle_par": utilisateur.nom,
    })
    return {"id": message.id, "epingle": True}


@router.post("/cercles/{cercle_id}/messages/{message_id}/desepingler")
async def desepingler_message(
    request: Request,
    cercle_id: int,
    message_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    cercle = session.get(CercleEtude, cercle_id)
    if not utilisateur or not cercle:
        raise HTTPException(status_code=404, detail="Cercle introuvable.")
    if not _peut_gerer_cercle(cercle, utilisateur):
        raise HTTPException(status_code=403, detail="Action reservee au createur du cercle ou a un administrateur.")

    message = session.get(MessageCercle, message_id)
    if not message or message.cercle_id != cercle_id:
        raise HTTPException(status_code=404, detail="Message introuvable.")

    message.epingle = False
    message.epingle_par_id = None
    message.date_epinglage = None
    session.add(message)
    session.commit()

    await gestionnaire.diffuser(cercle_id, {"type": "desepinglage", "id": message.id})
    return {"id": message.id, "epingle": False}


@router.get("/cercles/{cercle_id}/messages/{message_id}/thread")
def voir_thread(request: Request, cercle_id: int, message_id: int, session: Session = Depends(get_session)):
    """Renvoie le message parent et toutes ses reponses (§6 du brief),
    charge a la demande quand l'utilisateur ouvre le panneau de fil de
    discussion plutot qu'a l'ouverture du salon (§28 : chargement
    progressif des threads)."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        raise HTTPException(status_code=401, detail="Non connecte.")
    if not _a_acces_cercle(session, cercle_id, utilisateur.id):
        raise HTTPException(status_code=403, detail="Vous n'etes pas membre de ce cercle.")

    parent = session.get(MessageCercle, message_id)
    if not parent or parent.cercle_id != cercle_id:
        raise HTTPException(status_code=404, detail="Message introuvable.")

    auteur_parent = session.get(Utilisateur, parent.auteur_id)
    lignes_reponses = session.exec(
        select(MessageCercle, Utilisateur)
        .where(MessageCercle.parent_message_id == message_id)
        .where(MessageCercle.auteur_id == Utilisateur.id)
        .where(MessageCercle.supprime == False)  # noqa: E712
        .order_by(MessageCercle.date_envoi)
    ).all()

    message_ids = [parent.id] + [m.id for m, _u in lignes_reponses]
    reactions = session.exec(
        select(MessageReaction).where(MessageReaction.message_id.in_(message_ids or [-1]))
    ).all()
    reactions_par_message = {}
    for reaction in reactions:
        par_type = reactions_par_message.setdefault(reaction.message_id, {})
        par_type.setdefault(reaction.type_reaction.value, {"type_reaction": reaction.type_reaction.value, "total": 0, "mienne": False})
        par_type[reaction.type_reaction.value]["total"] += 1
        if reaction.utilisateur_id == utilisateur.id:
            par_type[reaction.type_reaction.value]["mienne"] = True

    def _reactions_serialisees(message_id: int) -> list[dict]:
        par_type = reactions_par_message.get(message_id, {})
        return [par_type[t.value] for t in TypeReaction if t.value in par_type]

    def _serialiser(m: MessageCercle, u: Utilisateur) -> dict:
        return {
            "id": m.id,
            "auteur": u.nom,
            "auteur_id": u.id,
            "auteur_a_une_photo": bool(u.photo_chemin),
            "contenu": m.contenu,
            "date_envoi": m.date_envoi.isoformat(),
            "modifie": m.date_modification is not None,
            "est_moi": u.id == utilisateur.id,
            "reactions": _reactions_serialisees(m.id),
        }

    return {
        "parent": _serialiser(parent, auteur_parent) if auteur_parent else None,
        "reponses": [_serialiser(m, u) for m, u in lignes_reponses],
    }


@router.get("/cercles/{cercle_id}/membres/{utilisateur_id}/profil")
def profil_membre_cercle(
    cercle_id: int,
    utilisateur_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    """Profil visible uniquement entre personnes ayant acces au meme cercle.

    Le parcours est restitue dans la meme hierarchie partout :
    Universite -> Composante -> Domaine -> Mention -> Parcours -> Niveau.
    La coherence academique provient du service centralise afin de ne pas
    avoir une version differente entre profil, recherche et adhesion.
    """
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        raise HTTPException(status_code=401, detail="Non connecte.")
    if not _a_acces_cercle(session, cercle_id, utilisateur.id):
        raise HTTPException(status_code=403, detail="Vous n'avez pas acces a ce cercle.")

    cible = session.get(Utilisateur, utilisateur_id)
    if not cible or not _a_acces_cercle(session, cercle_id, utilisateur_id):
        raise HTTPException(status_code=404, detail="Utilisateur introuvable dans ce cercle.")

    profil = referentiel_academique.contexte_profil_academique(cible, session)

    en_ligne = any(
        u["utilisateur_id"] == utilisateur_id
        for u in gestionnaire.utilisateurs_actifs(cercle_id)
    )

    return {
        "id": cible.id,
        "nom": cible.nom,
        "a_une_photo": bool(cible.photo_chemin),
        "en_ligne": en_ligne,
        "academique": referentiel_academique.serialiser_profil_academique(profil),
        "bio": cible.bio,
    }

@router.get("/cercles/{cercle_id}/recherche")
def rechercher_messages(request: Request, cercle_id: int, q: str = "", session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle or cercle.statut != StatutCercle.ACTIF:
        return RedirectResponse("/cercles", status_code=303)
    if not _a_acces_cercle(session, cercle_id, utilisateur.id):
        return RedirectResponse("/cercles", status_code=303)

    resultats = []
    terme = q.strip()
    if terme:
        lignes = session.exec(
            select(MessageCercle, Utilisateur)
            .where(MessageCercle.cercle_id == cercle_id)
            .where(MessageCercle.auteur_id == Utilisateur.id)
            .where(MessageCercle.supprime == False)  # noqa: E712
            .where(MessageCercle.contenu.ilike(f"%{terme}%"))
            .order_by(MessageCercle.date_envoi.desc())
        ).all()
        resultats = [{"auteur": u.nom, "contenu": m.contenu, "date_envoi": m.date_envoi} for m, u in lignes]

    return templates.TemplateResponse(
        request,
        "cercle_recherche.html",
        {"cercle": cercle, "utilisateur": utilisateur, "terme": terme, "resultats": resultats},
    )


@router.websocket("/cercles/{cercle_id}/ws")
async def salon_cercle_websocket(websocket: WebSocket, cercle_id: int):
    user_id = websocket.session.get("user_id")
    if not user_id:
        # Refuse la connexion avant meme le handshake WebSocket si personne
        # n'est connecte (pas de session valide).
        await websocket.close(code=4401)
        return

    with Session(engine) as session:
        utilisateur = session.get(Utilisateur, user_id)
        cercle = session.get(CercleEtude, cercle_id)
        if (
            not utilisateur
            or utilisateur.banni
            or not cercle
            or cercle.statut != StatutCercle.ACTIF
        ):
            await websocket.close(code=4403)
            return
        if not _a_acces_cercle(session, cercle_id, user_id):
            await websocket.close(code=4403)
            return

        abonnement = subscription.obtenir_abonnement(session, user_id)
        if abonnement:
            abonnement = subscription.synchroniser_expiration(session, abonnement)
        if not subscription.acces_premium_valide(abonnement):
            # 4402, en echo au code HTTP 402 Payment Required : pas de
            # redirection possible en WebSocket, donc on ferme simplement
            # la connexion. La page /cercles/{id} (HTTP) bloque deja
            # l'affichage du salon avant meme d'essayer d'ouvrir ce socket.
            await websocket.close(code=4402)
            return

        nom_auteur = utilisateur.nom
        # Meme precaution que nom_auteur ci-dessus : capture en scalaire
        # AVANT la fermeture de cette session (bloc `with`), sinon
        # acceder a utilisateur.photo_chemin plus bas (apres la
        # fermeture) leverait DetachedInstanceError.
        auteur_a_une_photo = bool(utilisateur.photo_chemin)

    await gestionnaire.connecter(cercle_id, websocket, user_id, nom_auteur)
    await gestionnaire.diffuser_presence(cercle_id)
    try:
        while True:
            donnees_recues = await websocket.receive_json()
            contenu = (donnees_recues.get("contenu") or "").strip()[:LONGUEUR_MAX_MESSAGE]
            if not contenu:
                continue
            # parent_message_id : presence d'une reponse (§5). mentions :
            # liste d'IDs choisis explicitement par l'autocompletion cote
            # client (§7) — on ne re-parse jamais le texte pour deviner
            # qui est mentionne, ce qui serait fragile (accents, noms
            # composes, homonymes) et non fiable pour declencher une
            # notification.
            parent_message_id = donnees_recues.get("parent_message_id")
            mentions_demandees = donnees_recues.get("mentions") or []

            with Session(engine) as session:
                parent = None
                if parent_message_id is not None:
                    parent = session.get(MessageCercle, parent_message_id)
                    # Reponse invalide (parent inexistant/supprime/autre
                    # cercle, ou reponse-a-une-reponse) : on degrade
                    # silencieusement en message normal plutot que de
                    # rejeter tout l'envoi pour une incoherence mineure.
                    if not parent or parent.cercle_id != cercle_id or parent.supprime or parent.parent_message_id is not None:
                        parent_message_id = None
                        parent = None

                message = MessageCercle(
                    cercle_id=cercle_id,
                    auteur_id=user_id,
                    contenu=contenu,
                    parent_message_id=parent_message_id,
                )
                session.add(message)
                session.commit()
                session.refresh(message)

                # Mentions : ne garder que des IDs reellement membres de ce
                # cercle (jamais confiance au client), sans doublon, sans
                # se mentionner soi-meme.
                ids_membres_valides = {
                    m.utilisateur_id
                    for m in session.exec(select(MembreCercle).where(MembreCercle.cercle_id == cercle_id)).all()
                }
                mentions_valides = {
                    int(uid) for uid in mentions_demandees
                    if isinstance(uid, (int, str)) and str(uid).isdigit() and int(uid) in ids_membres_valides and int(uid) != user_id
                }
                for uid_mentionne in mentions_valides:
                    session.add(MessageMention(message_id=message.id, utilisateur_mentionne_id=uid_mentionne))
                session.commit()
                if mentions_valides:
                    cercle_actuel = session.get(CercleEtude, cercle_id)
                    nom_cercle = cercle_actuel.nom if cercle_actuel else "un cercle"
                    for uid_mentionne in mentions_valides:
                        _creer_notification(
                            session,
                            destinataire_id=uid_mentionne,
                            type_notification=TypeNotification.MENTION,
                            contenu=f"{nom_auteur} vous a mentionne dans {nom_cercle}",
                            acteur_id=user_id,
                            cercle_id=cercle_id,
                            message_id=message.id,
                        )

                if parent is not None and parent.auteur_id != user_id:
                    _creer_notification(
                        session,
                        destinataire_id=parent.auteur_id,
                        type_notification=TypeNotification.REPONSE_MESSAGE,
                        contenu=f"{nom_auteur} a repondu a votre message",
                        acteur_id=user_id,
                        cercle_id=cercle_id,
                        message_id=message.id,
                    )

                # Capture des valeurs scalaires AVANT la fermeture de la
                # session (fin du bloc `with`) : les commits precedents
                # (message, mentions) ont expire les attributs de `message`
                # (expire_on_commit par defaut), donc y acceder apres la
                # fermeture de la session levait DetachedInstanceError et
                # faisait planter toute la diffusion websocket a chaque
                # envoi (voir logs Render du 25/08).
                id_message = message.id
                date_envoi_message = message.date_envoi

            await gestionnaire.diffuser(cercle_id, {
                "type": "message",
                "id": id_message,
                "auteur": nom_auteur,
                "auteur_id": user_id,
                "auteur_a_une_photo": auteur_a_une_photo,
                "contenu": contenu,
                "parent_message_id": parent_message_id,
                "mentions": list(mentions_valides),
                "date_envoi": date_envoi_message.isoformat(),
            })
    except WebSocketDisconnect:
        gestionnaire.deconnecter(cercle_id, websocket)
        await gestionnaire.diffuser_presence(cercle_id)
