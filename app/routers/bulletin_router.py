"""Gestion des bulletins officiels et téléchargement familial sécurisé."""

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..auth import utilisateur_courant
from ..bulletins import (
    construire_snapshot_bulletin,
    generer_pdf_bulletin,
    lire_snapshot_bulletin,
    normaliser_periode,
)
from ..csrf import verifier_csrf
from ..database import get_session
from ..models import (
    BulletinScolaire,
    BulletinScolaireEvenement,
    Cours,
    Devoir,
    InscriptionCours,
    LienResponsableEleve,
    RoleUtilisateur,
    Utilisateur,
)
from ..templating import templates
from .classe_router import _peut_gerer_cours

router = APIRouter()


def _url_bulletins(cours_id: int, *, erreur: str | None = None, succes: str | None = None) -> str:
    url = f"/classe/{cours_id}/bulletins"
    if erreur:
        url += f"?erreur={erreur}"
    elif succes:
        url += f"?ok={succes}"
    return url


def _periode_canonique(session: Session, cours_id: int, saisie: str) -> str | None:
    valeur = normaliser_periode(saisie)
    if not valeur:
        return None
    devoirs = session.exec(
        select(Devoir).where(
            Devoir.cours_id == cours_id,
            Devoir.archive == False,  # noqa: E712
        ).order_by(Devoir.date_creation, Devoir.id)
    ).all()
    for devoir in devoirs:
        periode = normaliser_periode(devoir.periode)
        if periode and periode.casefold() == valeur.casefold():
            return periode
    return None


def _evenement(
    bulletin_id: int,
    acteur_id: int | None,
    action: str,
    details: dict,
) -> BulletinScolaireEvenement:
    return BulletinScolaireEvenement(
        bulletin_id=bulletin_id,
        acteur_id=acteur_id,
        action=action,
        details_json=json.dumps(details, ensure_ascii=False, separators=(",", ":")),
    )


@router.get("/classe/{cours_id}/bulletins")
def gestion_bulletins(
    request: Request,
    cours_id: int,
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    cours = session.get(Cours, cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur):
        return RedirectResponse("/classe", status_code=303)

    inscriptions = session.exec(
        select(InscriptionCours, Utilisateur)
        .where(
            InscriptionCours.cours_id == cours_id,
            InscriptionCours.utilisateur_id == Utilisateur.id,
        )
        .order_by(Utilisateur.nom)
    ).all()
    eleves = [eleve for _inscription, eleve in inscriptions]

    devoirs = session.exec(
        select(Devoir).where(
            Devoir.cours_id == cours_id,
            Devoir.archive == False,  # noqa: E712
        ).order_by(Devoir.date_creation, Devoir.id)
    ).all()
    periodes = []
    periodes_vues = set()
    for devoir in devoirs:
        periode = normaliser_periode(devoir.periode)
        if periode and periode.casefold() not in periodes_vues:
            periodes.append(periode)
            periodes_vues.add(periode.casefold())

    bulletins_modeles = session.exec(
        select(BulletinScolaire)
        .where(BulletinScolaire.cours_id == cours_id)
        .order_by(BulletinScolaire.date_modification.desc(), BulletinScolaire.id.desc())
        .limit(300)
    ).all()
    ids_eleves_bulletins = sorted({item.utilisateur_id for item in bulletins_modeles})
    eleves_par_id = (
        {
            eleve.id: eleve
            for eleve in session.exec(
                select(Utilisateur).where(Utilisateur.id.in_(ids_eleves_bulletins))
            ).all()
        }
        if ids_eleves_bulletins else {}
    )
    ids_bulletins = [item.id for item in bulletins_modeles if item.id is not None]
    evenements = (
        session.exec(
            select(BulletinScolaireEvenement)
            .where(BulletinScolaireEvenement.bulletin_id.in_(ids_bulletins))
            .order_by(BulletinScolaireEvenement.date_evenement.desc())
            .limit(600)
        ).all()
        if ids_bulletins else []
    )
    historique_par_id: dict[int, list[BulletinScolaireEvenement]] = {}
    for evenement in evenements:
        historique_par_id.setdefault(evenement.bulletin_id, []).append(evenement)

    bulletins = [
        {
            "bulletin": bulletin,
            "eleve": eleves_par_id.get(bulletin.utilisateur_id),
            "snapshot": lire_snapshot_bulletin(bulletin.snapshot_json),
            "historique": historique_par_id.get(bulletin.id, []),
        }
        for bulletin in bulletins_modeles
    ]
    return templates.TemplateResponse(
        request,
        "bulletins_cours.html",
        {
            "utilisateur": utilisateur,
            "cours": cours,
            "eleves": eleves,
            "periodes": periodes,
            "bulletins": bulletins,
            "erreur": request.query_params.get("erreur", ""),
            "succes": request.query_params.get("ok", ""),
        },
        headers={
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "X-Robots-Tag": "noindex, nofollow",
        },
    )


@router.post("/classe/{cours_id}/bulletins/creer")
def creer_bulletin(
    request: Request,
    cours_id: int,
    eleve_id: str = Form(...),
    periode: str = Form(...),
    appreciation: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    cours = session.get(Cours, cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur):
        return RedirectResponse("/classe", status_code=303)

    try:
        eleve_identifiant = int(eleve_id)
    except (TypeError, ValueError):
        return RedirectResponse(_url_bulletins(cours_id, erreur="eleve_invalide"), status_code=303)

    inscription = session.exec(
        select(InscriptionCours).where(
            InscriptionCours.cours_id == cours_id,
            InscriptionCours.utilisateur_id == eleve_identifiant,
        )
    ).first()
    eleve = session.get(Utilisateur, eleve_identifiant)
    periode_validee = _periode_canonique(session, cours_id, periode)
    if not inscription or not eleve or eleve.banni or not periode_validee:
        return RedirectResponse(_url_bulletins(cours_id, erreur="periode_ou_eleve_invalide"), status_code=303)

    appreciation_validee = (appreciation or "").strip()[:2000] or None
    bulletin = session.exec(
        select(BulletinScolaire).where(
            BulletinScolaire.cours_id == cours_id,
            BulletinScolaire.utilisateur_id == eleve_identifiant,
            BulletinScolaire.periode == periode_validee,
        )
    ).first()
    if bulletin:
        if bulletin.statut == "publie":
            return RedirectResponse(_url_bulletins(cours_id, erreur="bulletin_deja_publie"), status_code=303)
        ancienne_appreciation = bulletin.appreciation
        bulletin.appreciation = appreciation_validee
        bulletin.date_modification = datetime.utcnow()
        session.add(bulletin)
        session.add(_evenement(
            bulletin.id,
            utilisateur.id,
            "modification",
            {
                "appreciation_precedente": ancienne_appreciation,
                "appreciation_nouvelle": appreciation_validee,
            },
        ))
        session.commit()
        return RedirectResponse(_url_bulletins(cours_id, succes="brouillon_enregistre"), status_code=303)

    bulletin = BulletinScolaire(
        cours_id=cours_id,
        utilisateur_id=eleve_identifiant,
        periode=periode_validee,
        appreciation=appreciation_validee,
        cree_par_id=utilisateur.id,
        date_creation=datetime.utcnow(),
        date_modification=datetime.utcnow(),
    )
    session.add(bulletin)
    try:
        session.flush()
        session.add(_evenement(
            bulletin.id,
            utilisateur.id,
            "creation",
            {"periode": periode_validee, "eleve_id": eleve_identifiant},
        ))
        session.commit()
    except IntegrityError:
        session.rollback()
        return RedirectResponse(_url_bulletins(cours_id, erreur="bulletin_existant"), status_code=303)
    return RedirectResponse(_url_bulletins(cours_id, succes="brouillon_cree"), status_code=303)


@router.post("/classe/bulletins/{bulletin_id}/modifier")
def modifier_bulletin(
    request: Request,
    bulletin_id: int,
    appreciation: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    bulletin = session.get(BulletinScolaire, bulletin_id)
    cours = session.get(Cours, bulletin.cours_id) if bulletin else None
    if not bulletin or not cours or not _peut_gerer_cours(cours, utilisateur):
        return RedirectResponse("/classe", status_code=303)
    if bulletin.statut != "brouillon":
        return RedirectResponse(_url_bulletins(cours.id, erreur="bulletin_deja_publie"), status_code=303)

    nouvelle_appreciation = (appreciation or "").strip()[:2000] or None
    ancienne_appreciation = bulletin.appreciation
    bulletin.appreciation = nouvelle_appreciation
    bulletin.date_modification = datetime.utcnow()
    session.add(bulletin)
    session.add(_evenement(
        bulletin.id,
        utilisateur.id,
        "modification",
        {
            "appreciation_precedente": ancienne_appreciation,
            "appreciation_nouvelle": nouvelle_appreciation,
        },
    ))
    session.commit()
    return RedirectResponse(_url_bulletins(cours.id, succes="brouillon_enregistre"), status_code=303)


@router.post("/classe/bulletins/{bulletin_id}/publier")
def publier_bulletin(
    request: Request,
    bulletin_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    bulletin = session.get(BulletinScolaire, bulletin_id)
    cours = session.get(Cours, bulletin.cours_id) if bulletin else None
    eleve = session.get(Utilisateur, bulletin.utilisateur_id) if bulletin else None
    if not bulletin or not cours or not eleve or not _peut_gerer_cours(cours, utilisateur):
        return RedirectResponse("/classe", status_code=303)
    if bulletin.statut != "brouillon":
        return RedirectResponse(_url_bulletins(cours.id, erreur="bulletin_deja_publie"), status_code=303)
    if not session.exec(
        select(InscriptionCours).where(
            InscriptionCours.cours_id == cours.id,
            InscriptionCours.utilisateur_id == eleve.id,
        )
    ).first():
        return RedirectResponse(_url_bulletins(cours.id, erreur="eleve_non_inscrit"), status_code=303)

    maintenant = datetime.utcnow()
    try:
        snapshot = construire_snapshot_bulletin(
            session,
            cours,
            eleve,
            bulletin.periode,
            bulletin.appreciation,
            publie_le=maintenant,
        )
    except ValueError:
        return RedirectResponse(_url_bulletins(cours.id, erreur="aucune_note_corrigee"), status_code=303)

    bulletin.statut = "publie"
    bulletin.publie_par_id = utilisateur.id
    bulletin.date_publication = maintenant
    bulletin.date_modification = maintenant
    bulletin.snapshot_json = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    session.add(bulletin)
    session.add(_evenement(
        bulletin.id,
        utilisateur.id,
        "publication",
        {"snapshot": snapshot},
    ))
    session.commit()
    return RedirectResponse(_url_bulletins(cours.id, succes="bulletin_publie"), status_code=303)


@router.post("/classe/bulletins/{bulletin_id}/reouvrir")
def reouvrir_bulletin(
    request: Request,
    bulletin_id: int,
    motif: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    bulletin = session.get(BulletinScolaire, bulletin_id)
    cours = session.get(Cours, bulletin.cours_id) if bulletin else None
    if not bulletin or not cours or not _peut_gerer_cours(cours, utilisateur):
        return RedirectResponse("/classe", status_code=303)
    if bulletin.statut != "publie":
        return RedirectResponse(_url_bulletins(cours.id, erreur="bulletin_non_publie"), status_code=303)

    motif_valide = " ".join((motif or "").split())[:500]
    if not motif_valide:
        return RedirectResponse(_url_bulletins(cours.id, erreur="motif_requis"), status_code=303)

    ancien_snapshot = lire_snapshot_bulletin(bulletin.snapshot_json)
    session.add(_evenement(
        bulletin.id,
        utilisateur.id,
        "reouverture",
        {
            "motif": motif_valide,
            "snapshot_precedent": ancien_snapshot or bulletin.snapshot_json,
            "date_publication_precedente": (
                bulletin.date_publication.isoformat()
                if bulletin.date_publication else None
            ),
        },
    ))
    bulletin.statut = "brouillon"
    bulletin.publie_par_id = None
    bulletin.date_publication = None
    bulletin.snapshot_json = "{}"
    bulletin.date_modification = datetime.utcnow()
    session.add(bulletin)
    session.commit()
    return RedirectResponse(_url_bulletins(cours.id, succes="bulletin_reouvert"), status_code=303)


def responsable_autorise_bulletin(
    session: Session,
    utilisateur: Optional[Utilisateur],
    bulletin: BulletinScolaire,
) -> bool:
    """Autorise seulement le responsable lié activement à l'élève du bulletin."""
    if (
        not utilisateur
        or utilisateur.role != RoleUtilisateur.RESPONSABLE
        or utilisateur.profil_souhaite != "responsable"
        or bulletin.statut != "publie"
    ):
        return False
    return session.exec(
        select(LienResponsableEleve).where(
            LienResponsableEleve.responsable_id == utilisateur.id,
            LienResponsableEleve.eleve_id == bulletin.utilisateur_id,
            LienResponsableEleve.statut == "actif",
        )
    ).first() is not None


@router.get("/famille/bulletins/{bulletin_id}/telecharger")
def telecharger_bulletin_famille(
    request: Request,
    bulletin_id: int,
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    bulletin = session.get(BulletinScolaire, bulletin_id)
    if not bulletin:
        return RedirectResponse("/famille", status_code=303)
    if utilisateur.role != RoleUtilisateur.RESPONSABLE or utilisateur.profil_souhaite != "responsable":
        return RedirectResponse("/dashboard", status_code=303)
    if not responsable_autorise_bulletin(session, utilisateur, bulletin):
        return RedirectResponse("/famille", status_code=303)

    snapshot = lire_snapshot_bulletin(bulletin.snapshot_json)
    if not snapshot:
        return RedirectResponse("/famille", status_code=303)
    pdf = generer_pdf_bulletin(snapshot)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="bulletin-mitaridala-{bulletin.id}.pdf"',
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "X-Robots-Tag": "noindex, nofollow",
        },
    )
