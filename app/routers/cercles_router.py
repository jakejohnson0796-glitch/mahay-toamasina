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

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, FileResponse
from sqlmodel import Session, select, or_

from ..database import get_session, engine
from ..templating import templates
from ..csrf import verifier_csrf
from ..models import CercleEtude, MembreCercle, MessageCercle, SignalementMessage, Filiere, Utilisateur, RoleUtilisateur, DemandeAdhesionCercle, StatutDemandeAdhesion, ThemeDuJour
from ..auth import utilisateur_courant
from ..ws_manager import gestionnaire
from ..dependencies import acces_premium_ou_redirection
from ..storage import sauvegarder_fichier, obtenir_url_telechargement, stockage_distant_actif, FichierInvalide
from .. import subscription
from .. import theme_service

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


def _est_membre(session: Session, cercle_id: int, utilisateur_id: int) -> bool:
    return session.exec(
        select(MembreCercle).where(
            MembreCercle.cercle_id == cercle_id,
            MembreCercle.utilisateur_id == utilisateur_id,
        )
    ).first() is not None


def _est_admin(utilisateur: Optional[Utilisateur]) -> bool:
    return bool(utilisateur and utilisateur.role == RoleUtilisateur.ADMIN)


def _peut_gerer_cercle(cercle: CercleEtude, utilisateur: Optional[Utilisateur]) -> bool:
    """Createur du cercle (uniquement le sien) ou admin (n'importe
    lequel) — utilise pour : voir les membres, voir/traiter les
    demandes, retirer un membre, supprimer le cercle, ajouter un membre
    directement par numero. Reverifie a CHAQUE appel de route, jamais
    fait confiance a ce que l'interface affiche ou masque."""
    if not utilisateur:
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


def _assurer_membres_admins(session: Session, cercle_id: int) -> None:
    """Garantit que TOUS les administrateurs globaux ont une entree
    MembreCercle reelle pour ce cercle (pas juste un bypass de
    permission) : c'est ce qui leur permet par exemple de voir/participer
    au chat, dont l'acces est conditionne a `membre` dans salon_cercle().
    Hierarchie voulue : ADMIN_GLOBAL > OWNER, donc l'admin doit avoir
    acces a n'importe quel cercle sans avoir a demander a le rejoindre.

    Idempotent : n'insere que les admins qui n'ont pas deja de ligne
    (pas de doublon), qu'ils viennent d'etre crees ou que ce cercle
    existait deja avant l'introduction de cette regle."""
    deja_membres_ids = {
        m.utilisateur_id
        for m in session.exec(select(MembreCercle).where(MembreCercle.cercle_id == cercle_id)).all()
    }
    admins = session.exec(select(Utilisateur).where(Utilisateur.role == RoleUtilisateur.ADMIN)).all()
    a_ajouter = [a for a in admins if a.id not in deja_membres_ids]
    if not a_ajouter:
        return
    for admin in a_ajouter:
        session.add(MembreCercle(cercle_id=cercle_id, utilisateur_id=admin.id))
    session.commit()


@router.get("/cercles")
def liste_cercles(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    cercles = session.exec(select(CercleEtude).order_by(CercleEtude.date_creation.desc())).all()
    filieres = session.exec(select(Filiere)).all()

    # Meme filet de securite que salon_cercle()/voir_membres() : sans cet
    # appel, un admin qui n'a pas encore ouvert individuellement un cercle
    # (ou qui vient d'etre promu admin) n'a pas encore de ligne MembreCercle
    # reelle pour ce cercle, et cette liste globale l'affichait alors a tort
    # comme non-membre — d'ou les boutons "Demander a rejoindre" / "Demande
    # en attente" vus par un Admin. On le fait ici, une fois par cercle,
    # avant de calculer est_membre/en_attente ci-dessous.
    if _est_admin(utilisateur):
        for cercle in cercles:
            _assurer_membres_admins(session, cercle.id)

    cercles_avec_info = []
    for cercle in cercles:
        nb_membres = len(
            session.exec(select(MembreCercle).where(MembreCercle.cercle_id == cercle.id)).all()
        )
        est_membre = _est_membre(session, cercle.id, utilisateur.id) if utilisateur else False
        en_attente = bool(
            utilisateur and not est_membre and _demande_en_attente(session, cercle.id, utilisateur.id)
        )
        cercles_avec_info.append({
            "cercle": cercle,
            "nb_membres": nb_membres,
            "est_membre": est_membre,
            "en_attente": en_attente,
            "peut_gerer": _peut_gerer_cercle(cercle, utilisateur),
        })

    return templates.TemplateResponse(
        request,
        "cercles_list.html",
        {
            "cercles_avec_info": cercles_avec_info,
            "filieres": filieres,
            "utilisateur": utilisateur,
            "theme_du_jour": theme_service.get_theme_du_jour(),
        },
    )


@router.post("/cercles/creer")
def creer_cercle(
    request: Request,
    nom: str = Form(...),
    description: Optional[str] = Form(None),
    filiere_id: Optional[int] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

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
    nb_cercles_existants = len(
        session.exec(select(CercleEtude).where(CercleEtude.createur_id == utilisateur.id)).all()
    )
    if nb_cercles_existants >= MAX_CERCLES_PAR_UTILISATEUR:
        filieres = session.exec(select(Filiere)).all()
        cercles = session.exec(select(CercleEtude).order_by(CercleEtude.date_creation.desc())).all()
        cercles_avec_info = []
        for c in cercles:
            nb_membres = len(session.exec(select(MembreCercle).where(MembreCercle.cercle_id == c.id)).all())
            cercles_avec_info.append({
                "cercle": c, "nb_membres": nb_membres,
                "est_membre": _est_membre(session, c.id, utilisateur.id),
                "en_attente": False,
                "peut_gerer": _peut_gerer_cercle(c, utilisateur),
            })
        return templates.TemplateResponse(
            request,
            "cercles_list.html",
            {
                "cercles_avec_info": cercles_avec_info, "filieres": filieres, "utilisateur": utilisateur,
                "erreur": f"Vous avez deja atteint la limite de {MAX_CERCLES_PAR_UTILISATEUR} cercles crees.",
            },
        )

    cercle = CercleEtude(
        nom=nom,
        description=description or None,
        filiere_id=filiere_id,
        createur_id=utilisateur.id,
    )
    session.add(cercle)
    session.commit()
    session.refresh(cercle)

    # Le createur rejoint automatiquement son propre cercle.
    session.add(MembreCercle(cercle_id=cercle.id, utilisateur_id=utilisateur.id))
    session.commit()

    # Hierarchie ADMIN_GLOBAL > OWNER : tout administrateur global doit
    # avoir acces automatique a ce nouvel espace, sans avoir a demander a
    # le rejoindre (voir _assurer_membres_admins).
    _assurer_membres_admins(session, cercle.id)

    return RedirectResponse(f"/cercles/{cercle.id}", status_code=303)


@router.post("/cercles/{cercle_id}/demander")
def demander_adhesion(request: Request, cercle_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    """Cree une demande d'adhesion EN_ATTENTE (remplace l'ancienne
    adhesion immediate). L'utilisateur ne devient PAS membre ici — il
    faut que le createur du cercle ou un admin l'accepte (voir
    accepter_demande ci-dessous)."""
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle:
        return RedirectResponse("/cercles", status_code=303)

    # Defense en profondeur : meme si l'interface ne devrait jamais
    # proposer ce bouton a un Admin (voir liste_cercles/salon_cercle qui
    # l'assurent deja membre en amont), un appel direct sur cette route
    # (POST forge, ancienne page en cache, etc.) ne doit jamais faire
    # passer un Admin par le circuit de demande — il est rendu membre
    # immediatement, sans creation de DemandeAdhesionCercle.
    if _est_admin(utilisateur):
        _assurer_membres_admins(session, cercle_id)
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    if _est_membre(session, cercle_id, utilisateur.id):
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    # Empeche le doublon cote applicatif (verification rapide, UX claire) ;
    # l'index unique partiel en base (migration c4e91a2f7b6d) est le vrai
    # garde-fou en cas de requetes concurrentes.
    if not _demande_en_attente(session, cercle_id, utilisateur.id):
        session.add(DemandeAdhesionCercle(cercle_id=cercle_id, utilisateur_id=utilisateur.id))
        session.commit()

    return RedirectResponse("/cercles", status_code=303)


@router.get("/cercles/{cercle_id}/membres")
def voir_membres(request: Request, cercle_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle:
        return RedirectResponse("/cercles", status_code=303)

    if _est_admin(utilisateur):
        _assurer_membres_admins(session, cercle_id)

    # Seuls les membres du cercle (+ createur/admin, qui sont de toute
    # facon membres ou geres a part) peuvent voir la liste — un visiteur
    # externe non-membre n'a pas a voir qui est dans le cercle.
    if not _est_membre(session, cercle_id, utilisateur.id) and not _peut_gerer_cercle(cercle, utilisateur):
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
    compte MAHAY (on ne cree pas de compte a sa place)."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle:
        return RedirectResponse("/cercles", status_code=303)

    if not _peut_gerer_cercle(cercle, utilisateur):
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    cible = session.exec(select(Utilisateur).where(Utilisateur.telephone == telephone.strip())).first()
    if not cible:
        return RedirectResponse(f"/cercles/{cercle_id}/membres?erreur=utilisateur_introuvable", status_code=303)

    if not _est_membre(session, cercle_id, cible.id):
        session.add(MembreCercle(cercle_id=cercle_id, utilisateur_id=cible.id))
        session.commit()

    return RedirectResponse(f"/cercles/{cercle_id}/membres?ajoute=1", status_code=303)


@router.get("/cercles/{cercle_id}/demandes")
def voir_demandes(request: Request, cercle_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle:
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

    # Une demande deja traitee (acceptee/rejetee) ne peut pas etre
    # retraitee — evite les doubles clics / actions concurrentes qui
    # ajouteraient deux fois le membre ou ecraseraient une decision.
    if demande.statut == StatutDemandeAdhesion.EN_ATTENTE:
        demande.statut = StatutDemandeAdhesion.ACCEPTEE
        demande.date_traitement = datetime.utcnow()
        demande.traite_par_id = utilisateur.id
        session.add(demande)
        if not _est_membre(session, cercle_id, demande.utilisateur_id):
            session.add(MembreCercle(cercle_id=cercle_id, utilisateur_id=demande.utilisateur_id))
        session.commit()

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

    if demande.statut == StatutDemandeAdhesion.EN_ATTENTE:
        demande.statut = StatutDemandeAdhesion.REJETEE
        demande.date_traitement = datetime.utcnow()
        demande.traite_par_id = utilisateur.id
        session.add(demande)
        session.commit()

    return RedirectResponse(f"/cercles/{cercle_id}/demandes", status_code=303)


@router.post("/cercles/{cercle_id}/quitter")
def quitter_cercle(request: Request, cercle_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle:
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
    if not cercle:
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
    if not cercle:
        return RedirectResponse("/cercles", status_code=303)

    if not _peut_gerer_cercle(cercle, utilisateur):
        return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    # Nettoyage complet : membres, demandes, messages (+ signalements
    # associes) et enfin le cercle lui-meme — evite de laisser des lignes
    # orphelines en base qui referenceraient un cercle_id inexistant.
    for membre in session.exec(select(MembreCercle).where(MembreCercle.cercle_id == cercle_id)).all():
        session.delete(membre)
    for demande in session.exec(select(DemandeAdhesionCercle).where(DemandeAdhesionCercle.cercle_id == cercle_id)).all():
        session.delete(demande)
    messages = session.exec(select(MessageCercle).where(MessageCercle.cercle_id == cercle_id)).all()
    for message in messages:
        for signalement in session.exec(select(SignalementMessage).where(SignalementMessage.message_id == message.id)).all():
            session.delete(signalement)
        session.delete(message)
    # cercle_id est nullable sur ThemeDuJour (un theme du jour peut exister
    # sans cercle dedie) : on detache plutot que supprimer, pour garder
    # l'historique des themes passes meme si leur cercle est efface.
    for theme_jour in session.exec(select(ThemeDuJour).where(ThemeDuJour.cercle_id == cercle_id)).all():
        theme_jour.cercle_id = None
        session.add(theme_jour)
    session.delete(cercle)
    session.commit()

    return RedirectResponse("/cercles?supprime=1", status_code=303)


@router.get("/cercles/{cercle_id}")
def salon_cercle(request: Request, cercle_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle:
        return RedirectResponse("/cercles", status_code=303)

    # Filet de securite pour les cercles crees AVANT cette regle (ou si un
    # nouvel admin a ete cree apres coup) : garantit que l'admin courant a
    # bien une adhesion reelle avant qu'on calcule `membre` juste apres.
    if _est_admin(utilisateur):
        _assurer_membres_admins(session, cercle_id)

    membre = _est_membre(session, cercle_id, utilisateur.id)
    en_attente = bool(not membre and _demande_en_attente(session, cercle_id, utilisateur.id))

    messages = []
    if membre:
        lignes = session.exec(
            select(MessageCercle, Utilisateur)
            .where(MessageCercle.cercle_id == cercle_id)
            .where(MessageCercle.auteur_id == Utilisateur.id)
            .where(MessageCercle.supprime == False)  # noqa: E712 — comparaison SQLModel/SQLAlchemy, pas Python
            .order_by(MessageCercle.date_envoi)
        ).all()
        messages = [
            {
                "id": m.id,
                "auteur": u.nom,
                "auteur_id": u.id,
                "contenu": m.contenu,
                "piece_jointe_chemin": m.piece_jointe_chemin,
                "piece_jointe_nom": m.piece_jointe_nom,
                "est_moi": u.id == utilisateur.id,
            }
            for m, u in lignes
        ]

    return templates.TemplateResponse(
        request,
        "cercle_chat.html",
        {
            "cercle": cercle,
            "membre": membre,
            "en_attente": en_attente,
            "peut_gerer": _peut_gerer_cercle(cercle, utilisateur),
            "messages": messages,
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
    if not cercle:
        return RedirectResponse("/cercles", status_code=303)

    if _est_admin(utilisateur):
        _assurer_membres_admins(session, cercle_id)
    if not _est_membre(session, cercle_id, utilisateur.id):
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
        "contenu": "",
        "piece_jointe_nom": fichier.filename,
        "piece_jointe_url": f"/cercles/{cercle_id}/messages/{message.id}/piece-jointe",
    })

    return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)


@router.get("/cercles/{cercle_id}/messages/{message_id}/piece-jointe")
def telecharger_piece_jointe(request: Request, cercle_id: int, message_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    if _est_admin(utilisateur):
        _assurer_membres_admins(session, cercle_id)
    if not _est_membre(session, cercle_id, utilisateur.id):
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
    if not message or message.cercle_id != cercle_id or not _est_membre(session, cercle_id, utilisateur.id):
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


@router.get("/cercles/{cercle_id}/recherche")
def rechercher_messages(request: Request, cercle_id: int, q: str = "", session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle:
        return RedirectResponse("/cercles", status_code=303)
    if _est_admin(utilisateur):
        _assurer_membres_admins(session, cercle_id)
    if not _est_membre(session, cercle_id, utilisateur.id):
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
        if not utilisateur or not session.get(CercleEtude, cercle_id):
            await websocket.close(code=4403)
            return
        if utilisateur.role == RoleUtilisateur.ADMIN:
            _assurer_membres_admins(session, cercle_id)
        if not _est_membre(session, cercle_id, user_id):
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

    await gestionnaire.connecter(cercle_id, websocket, user_id, nom_auteur)
    await gestionnaire.diffuser_presence(cercle_id)
    try:
        while True:
            donnees_recues = await websocket.receive_json()
            contenu = (donnees_recues.get("contenu") or "").strip()[:LONGUEUR_MAX_MESSAGE]
            if not contenu:
                continue

            with Session(engine) as session:
                message = MessageCercle(cercle_id=cercle_id, auteur_id=user_id, contenu=contenu)
                session.add(message)
                session.commit()
                session.refresh(message)

            await gestionnaire.diffuser(cercle_id, {
                "type": "message",
                "id": message.id,
                "auteur": nom_auteur,
                "auteur_id": user_id,
                "contenu": contenu,
            })
    except WebSocketDisconnect:
        gestionnaire.deconnecter(cercle_id, websocket)
        await gestionnaire.diffuser_presence(cercle_id)
