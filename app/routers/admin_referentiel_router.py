"""
Ecrans admin du referentiel academique national : creer des Mention,
puis assigner mention_id (+ niveau pour les cercles) aux Filiere et
CercleEtude existants — jamais devine automatiquement (voir §44 du
brief refonte academique), toujours une action explicite d'un admin.

Distinct de admin_router.py (deja tres charge) pour garder ce nouveau
perimetre lisible independamment.
"""
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..auth import utilisateur_courant
from ..models import Utilisateur, RoleUtilisateur, Mention, Universite, Faculte, Filiere, CercleEtude, MembreCercle, RoleMembreCercle, StatutCercle, DemandeCreationCercle, StatutDemandeCreationCercle
from ..referentiel import NIVEAUX
from ..cercles_referentiel import assurer_cercles_pour_filiere
from ..web_utils import entier_ou_none
from .cercles_router import _assurer_membres_admins

router = APIRouter()


def _admin_requis(request: Request, session: Session) -> Optional[Utilisateur]:
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return None
    return utilisateur


@router.get("/admin/referentiel")
def page_referentiel(request: Request, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    universites = session.exec(select(Universite)).all()
    mentions = session.exec(select(Mention).order_by(Mention.nom)).all()
    filieres = session.exec(select(Filiere)).all()
    facultes = {f.id: f for f in session.exec(select(Faculte)).all()}

    nb_filieres_sans_mention = len([f for f in filieres if f.mention_id is None])

    return templates.TemplateResponse(
        request,
        "admin_referentiel.html",
        {
            "utilisateur": admin,
            "universites": universites,
            "mentions": mentions,
            "filieres": filieres,
            "facultes": facultes,
            "nb_filieres_sans_mention": nb_filieres_sans_mention,
        },
    )


@router.post("/admin/referentiel/mentions/creer")
def creer_mention(
    request: Request,
    nom: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    nom_nettoye = nom.strip()
    if not nom_nettoye:
        return RedirectResponse("/admin/referentiel?erreur=nom_requis", status_code=303)

    existe_deja = session.exec(select(Mention).where(Mention.nom == nom_nettoye)).first()
    if existe_deja:
        return RedirectResponse("/admin/referentiel?erreur=mention_existe_deja", status_code=303)

    session.add(Mention(nom=nom_nettoye))
    session.commit()
    return RedirectResponse("/admin/referentiel?ok=mention_creee", status_code=303)


@router.post("/admin/referentiel/filieres/{filiere_id}/assigner-mention")
def assigner_mention_filiere(
    request: Request,
    filiere_id: int,
    mention_id: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Assigne (ou retire, si mention_id vide) la mention d'une filiere
    existante. Toujours une action explicite d'un admin — jamais
    devine/auto-rempli (§44 du brief : "la normalisation doit etre
    faite avec prudence")."""
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    filiere = session.get(Filiere, filiere_id)
    if not filiere:
        return RedirectResponse("/admin/referentiel?erreur=filiere_introuvable", status_code=303)

    mention_id_nettoye = entier_ou_none(mention_id)
    if mention_id_nettoye:
        mention = session.get(Mention, mention_id_nettoye)
        if not mention:
            return RedirectResponse("/admin/referentiel?erreur=mention_introuvable", status_code=303)
        filiere.mention_id = mention.id
    else:
        filiere.mention_id = None

    session.add(filiere)
    session.commit()
    session.refresh(filiere)

    # Des que la mention est connue, la filiere peut recevoir ses 8
    # cercles nationaux (un par niveau) sans attendre qu'un etudiant en
    # demande un explicitement — voir cercles_referentiel.py. Aucun
    # effet si mention_id vient d'etre efface (filiere.mention_id est
    # alors None, assurer_cercles_pour_filiere ne fait rien).
    assurer_cercles_pour_filiere(session, filiere, admin)

    return RedirectResponse("/admin/referentiel?ok=filiere_mise_a_jour", status_code=303)


@router.get("/admin/referentiel/cercles")
def page_cercles_a_completer(request: Request, tous: bool = False, page: int = 1, session: Session = Depends(get_session)):
    """Liste les cercles existants pour lesquels mention_id et/ou
    niveau ne sont pas encore renseignes — etape prealable a la
    contrainte anti-doublon 'un seul cercle national actif par
    mention+filiere+niveau', qui ne s'applique qu'aux cercles ayant
    les 3 champs remplis (voir la migration correspondante).

    Filtre sur ACTIF par defaut (?tous=1 pour aussi voir les archives) :
    un cercle ARCHIVE (typiquement fusionne par
    scripts/dedupliquer_cercles_nationaux.py, voir cercles_referentiel.py)
    n'a plus besoin d'etre corrige ici, et melange visuellement avec les
    cercles actifs preterait facilement a confusion (deux lignes au
    meme nom, l'une active et l'autre archivee, indiscernables sans
    cette distinction — signale par Jake apres deploiement).

    PAGINEE (signale par Jake : page tres lente apres l'import du
    referentiel national) : le template cherchait auparavant la
    filiere de CHAQUE cercle par une recherche lineaire (`selectattr`)
    dans la liste ENTIERE des filieres — O(cercles x filieres), soit
    plus de 200 000 comparaisons avec les ~1200 cercles et ~180
    filieres qui existent desormais. Remplace par un dict {id: filiere}
    construit une fois ici (O(1) par lookup), plus une pagination pour
    ne jamais rendre des centaines de lignes en une fois."""
    TAILLE_PAGE = 50

    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    from ..models import StatutCercle
    from sqlmodel import func

    requete = select(CercleEtude)
    if not tous:
        requete = requete.where(CercleEtude.statut == StatutCercle.ACTIF)

    total_cercles = session.exec(select(func.count()).select_from(requete.subquery())).one()
    total_pages = max(1, (total_cercles + TAILLE_PAGE - 1) // TAILLE_PAGE)
    page_nettoyee = min(max(1, page), total_pages)

    cercles = session.exec(
        requete.order_by(CercleEtude.nom).offset((page_nettoyee - 1) * TAILLE_PAGE).limit(TAILLE_PAGE)
    ).all()
    filiere_par_id = {f.id: f for f in session.exec(select(Filiere)).all()}
    mentions = session.exec(select(Mention).order_by(Mention.nom)).all()

    return templates.TemplateResponse(
        request,
        "admin_cercles_referentiel.html",
        {
            "utilisateur": admin,
            "cercles": cercles,
            "filiere_par_id": filiere_par_id,
            "mentions": mentions,
            "niveaux": NIVEAUX,
            "tous": tous,
            "page": page_nettoyee,
            "total_pages": total_pages,
            "total_cercles": total_cercles,
        },
    )


@router.post("/admin/referentiel/cercles/{cercle_id}/assigner")
def assigner_cercle(
    request: Request,
    cercle_id: int,
    mention_id: Optional[str] = Form(None),
    niveau: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    cercle = session.get(CercleEtude, cercle_id)
    if not cercle:
        return RedirectResponse("/admin/referentiel/cercles?erreur=cercle_introuvable", status_code=303)

    niveau_nettoye = (niveau or "").strip() or None
    if niveau_nettoye and niveau_nettoye not in NIVEAUX:
        return RedirectResponse("/admin/referentiel/cercles?erreur=niveau_invalide", status_code=303)

    mention_id_nettoye = entier_ou_none(mention_id)
    if mention_id_nettoye:
        mention = session.get(Mention, mention_id_nettoye)
        if not mention:
            return RedirectResponse("/admin/referentiel/cercles?erreur=mention_introuvable", status_code=303)
        cercle.mention_id = mention.id
    else:
        cercle.mention_id = None

    cercle.niveau = niveau_nettoye

    # Verification anti-doublon (defense en profondeur — la migration
    # pose deja un index unique partiel cote base pour le meme cas) :
    # si les 3 champs sont desormais tous renseignes, s'assurer qu'aucun
    # AUTRE cercle actif n'a deja exactement cette combinaison.
    if cercle.mention_id and cercle.filiere_id and cercle.niveau:
        from ..models import StatutCercle
        doublon = session.exec(
            select(CercleEtude).where(
                CercleEtude.id != cercle.id,
                CercleEtude.mention_id == cercle.mention_id,
                CercleEtude.filiere_id == cercle.filiere_id,
                CercleEtude.niveau == cercle.niveau,
                CercleEtude.statut == StatutCercle.ACTIF,
            )
        ).first()
        if doublon:
            return RedirectResponse(
                f"/admin/referentiel/cercles?erreur=doublon&cercle_existant={doublon.id}", status_code=303
            )

    session.add(cercle)
    session.commit()
    return RedirectResponse("/admin/referentiel/cercles?ok=cercle_mis_a_jour", status_code=303)


@router.get("/admin/referentiel/demandes-creation")
def page_demandes_creation(request: Request, session: Session = Depends(get_session)):
    """Liste les demandes de creation de cercle national (§20-27 du
    brief "cercles nationaux"), en attente d'abord."""
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    demandes = session.exec(
        select(DemandeCreationCercle).order_by(
            DemandeCreationCercle.statut, DemandeCreationCercle.date_creation.desc()
        )
    ).all()

    utilisateurs = {u.id: u for u in session.exec(select(Utilisateur)).all()}
    filieres = {f.id: f for f in session.exec(select(Filiere)).all()}
    mentions = {m.id: m for m in session.exec(select(Mention)).all()}

    return templates.TemplateResponse(
        request,
        "admin_demandes_creation_cercle.html",
        {
            "utilisateur": admin,
            "demandes": demandes,
            "utilisateurs": utilisateurs,
            "filieres": filieres,
            "mentions": mentions,
        },
    )


@router.post("/admin/referentiel/demandes-creation/{demande_id}/approuver")
def approuver_demande_creation(
    request: Request,
    demande_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    demande = session.get(DemandeCreationCercle, demande_id)
    if not demande or demande.statut != StatutDemandeCreationCercle.EN_ATTENTE:
        return RedirectResponse("/admin/referentiel/demandes-creation", status_code=303)

    # Re-verification du doublon AU MOMENT DE L'APPROBATION (meme
    # principe que pour les demandes d'adhesion, §32 du brief) : une
    # autre demande equivalente a pu etre approuvee entre-temps, ou un
    # cercle cree par un autre chemin.
    doublon = session.exec(
        select(CercleEtude).where(
            CercleEtude.mention_id == demande.mention_id,
            CercleEtude.filiere_id == demande.filiere_id,
            CercleEtude.niveau == demande.niveau,
            CercleEtude.statut == StatutCercle.ACTIF,
        )
    ).first()
    if doublon:
        demande.statut = StatutDemandeCreationCercle.REJETEE
        demande.date_traitement = datetime.utcnow()
        demande.traite_par_id = admin.id
        demande.cercle_cree_id = doublon.id
        session.add(demande)
        session.commit()
        return RedirectResponse(
            f"/admin/referentiel/demandes-creation?erreur=doublon_survenu_entre_temps&cercle_existant={doublon.id}",
            status_code=303,
        )

    cercle = CercleEtude(
        nom=demande.nom,
        description=demande.description,
        mention_id=demande.mention_id,
        filiere_id=demande.filiere_id,
        niveau=demande.niveau,
        statut=StatutCercle.ACTIF,
        createur_id=demande.utilisateur_id,
    )
    session.add(cercle)
    session.commit()
    session.refresh(cercle)

    session.add(MembreCercle(cercle_id=cercle.id, utilisateur_id=demande.utilisateur_id, role=RoleMembreCercle.CREATEUR))
    session.commit()
    _assurer_membres_admins(session, cercle.id)

    demande.statut = StatutDemandeCreationCercle.APPROUVEE
    demande.date_traitement = datetime.utcnow()
    demande.traite_par_id = admin.id
    demande.cercle_cree_id = cercle.id
    session.add(demande)
    session.commit()

    return RedirectResponse("/admin/referentiel/demandes-creation?ok=approuvee", status_code=303)


@router.post("/admin/referentiel/demandes-creation/{demande_id}/rejeter")
def rejeter_demande_creation(
    request: Request,
    demande_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    demande = session.get(DemandeCreationCercle, demande_id)
    if demande and demande.statut == StatutDemandeCreationCercle.EN_ATTENTE:
        demande.statut = StatutDemandeCreationCercle.REJETEE
        demande.date_traitement = datetime.utcnow()
        demande.traite_par_id = admin.id
        session.add(demande)
        session.commit()

    return RedirectResponse("/admin/referentiel/demandes-creation?ok=rejetee", status_code=303)
