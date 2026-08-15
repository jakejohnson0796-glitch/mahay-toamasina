"""
Ecrans admin du referentiel academique national : creer des Mention,
puis assigner mention_id (+ niveau pour les cercles) aux Filiere et
CercleEtude existants — jamais devine automatiquement (voir §44 du
brief refonte academique), toujours une action explicite d'un admin.

Distinct de admin_router.py (deja tres charge) pour garder ce nouveau
perimetre lisible independamment.
"""
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..auth import utilisateur_courant
from ..models import Utilisateur, RoleUtilisateur, Mention, Universite, Faculte, Filiere, CercleEtude
from ..referentiel import NIVEAUX

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
    mention_id: Optional[int] = Form(None),
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

    if mention_id:
        mention = session.get(Mention, mention_id)
        if not mention:
            return RedirectResponse("/admin/referentiel?erreur=mention_introuvable", status_code=303)
        filiere.mention_id = mention.id
    else:
        filiere.mention_id = None

    session.add(filiere)
    session.commit()
    return RedirectResponse("/admin/referentiel?ok=filiere_mise_a_jour", status_code=303)


@router.get("/admin/referentiel/cercles")
def page_cercles_a_completer(request: Request, session: Session = Depends(get_session)):
    """Liste les cercles existants pour lesquels mention_id et/ou
    niveau ne sont pas encore renseignes — etape prealable a la
    contrainte anti-doublon 'un seul cercle national actif par
    mention+filiere+niveau', qui ne s'applique qu'aux cercles ayant
    les 3 champs remplis (voir la migration correspondante)."""
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    cercles = session.exec(select(CercleEtude).order_by(CercleEtude.nom)).all()
    filieres = session.exec(select(Filiere)).all()
    mentions = session.exec(select(Mention).order_by(Mention.nom)).all()

    return templates.TemplateResponse(
        request,
        "admin_cercles_referentiel.html",
        {
            "utilisateur": admin,
            "cercles": cercles,
            "filieres": filieres,
            "mentions": mentions,
            "niveaux": NIVEAUX,
        },
    )


@router.post("/admin/referentiel/cercles/{cercle_id}/assigner")
def assigner_cercle(
    request: Request,
    cercle_id: int,
    mention_id: Optional[int] = Form(None),
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

    if mention_id:
        mention = session.get(Mention, mention_id)
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
