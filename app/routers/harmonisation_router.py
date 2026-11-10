"""Espace indépendant d'harmonisation réservé aux enseignants vérifiés.

Les enseignants proposent et commentent les évolutions des cours. Seul un
administrateur peut accepter, refuser ou demander des précisions. Une version
acceptée est publiée directement sur la fiche du document dans la bibliothèque.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..auth import utilisateur_courant
from ..csrf import verifier_csrf
from ..database import get_session
from ..models import (
    DemandeMiseAJourCours,
    Document,
    EchangeDemandeMiseAJourCours,
    Notification,
    RoleUtilisateur,
    StatutDocument,
    StatutDemandeMiseAJourCours,
    TypeDocument,
    TypeNotification,
    Utilisateur,
)
from ..templating import templates

router = APIRouter()


def professeur_verifie(utilisateur: Optional[Utilisateur]) -> bool:
    return bool(
        utilisateur
        and utilisateur.role == RoleUtilisateur.PROFESSEUR
        and utilisateur.statut_verification_enseignant == "approuve"
    )


def administrateur_autorise(utilisateur: Optional[Utilisateur]) -> bool:
    return bool(utilisateur and utilisateur.role == RoleUtilisateur.ADMIN)


def _rediriger_professeur(etat: str) -> RedirectResponse:
    return RedirectResponse(f"/enseignant/harmonisation?etat={etat}", status_code=303)


def _document_eligible(session: Session, document_id: int) -> Optional[Document]:
    document = session.get(Document, document_id)
    if (
        not document
        or document.statut != StatutDocument.APPROUVE
        or document.type_document != TypeDocument.COURS
        or document.cercle_id is not None
    ):
        return None
    return document


def _notifier(
    session: Session,
    destinataire: Utilisateur,
    acteur_id: Optional[int],
    contenu: str,
    destination: str,
) -> None:
    session.add(
        Notification(
            destinataire_id=destinataire.id,
            type_notification=TypeNotification.HARMONISATION_COURS,
            contenu=contenu[:1000],
            acteur_id=acteur_id,
            url_destination=destination,
        )
    )


def _notifier_enseignants_et_admins(
    session: Session,
    demande: DemandeMiseAJourCours,
    document: Document,
    auteur: Utilisateur,
) -> None:
    resume = (
        f"Nouvelle proposition : {document.titre} · {document.matiere} · {auteur.nom}. "
        f"Motif : {demande.justification[:220]}"
    )
    enseignants = session.exec(
        select(Utilisateur).where(
            Utilisateur.role == RoleUtilisateur.PROFESSEUR,
            Utilisateur.statut_verification_enseignant == "approuve",
        )
    ).all()
    for enseignant in enseignants:
        if enseignant.id != auteur.id:
            _notifier(
                session,
                enseignant,
                auteur.id,
                resume,
                f"/enseignant/harmonisation/demandes/{demande.id}",
            )
    administrateurs = session.exec(
        select(Utilisateur).where(Utilisateur.role == RoleUtilisateur.ADMIN)
    ).all()
    for administrateur in administrateurs:
        _notifier(
            session,
            administrateur,
            auteur.id,
            resume,
            f"/admin/harmonisation-cours/demandes/{demande.id}",
        )


def _notifications_statut(
    session: Session,
    demande: DemandeMiseAJourCours,
    document: Optional[Document],
    acteur: Utilisateur,
    message: str,
) -> None:
    auteur = session.get(Utilisateur, demande.auteur_id)
    if auteur:
        titre = document.titre if document else "le cours"
        _notifier(
            session,
            auteur,
            acteur.id,
            f"{titre} : {message}",
            f"/enseignant/harmonisation/demandes/{demande.id}",
        )


def _details_demande(session: Session, demande: DemandeMiseAJourCours) -> dict:
    document = session.get(Document, demande.document_id)
    auteur = session.get(Utilisateur, demande.auteur_id)
    echanges = session.exec(
        select(EchangeDemandeMiseAJourCours)
        .where(EchangeDemandeMiseAJourCours.demande_id == demande.id)
        .order_by(EchangeDemandeMiseAJourCours.date_creation.asc())
    ).all()
    auteurs_ids = {e.auteur_id for e in echanges}
    utilisateurs = {}
    if auteurs_ids:
        utilisateurs = {
            u.id: u
            for u in session.exec(
                select(Utilisateur).where(Utilisateur.id.in_(auteurs_ids))
            ).all()
        }
    return {
        "demande": demande,
        "document": document,
        "auteur": auteur,
        "echanges": [
            {"echange": e, "auteur": utilisateurs.get(e.auteur_id)}
            for e in echanges
        ],
    }


def _ajouter_echange(
    session: Session,
    demande: DemandeMiseAJourCours,
    auteur: Utilisateur,
    message: str,
) -> None:
    session.add(
        EchangeDemandeMiseAJourCours(
            demande_id=demande.id,
            auteur_id=auteur.id,
            message=message.strip(),
        )
    )
    demande.date_modification = datetime.utcnow()
    if demande.statut == StatutDemandeMiseAJourCours.EN_ATTENTE.value:
        demande.statut = StatutDemandeMiseAJourCours.EN_DISCUSSION.value
    session.add(demande)


@router.get("/enseignant/harmonisation")
def page_harmonisation_professeur(
    request: Request,
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not professeur_verifie(utilisateur):
        return RedirectResponse("/", status_code=303)
    documents = session.exec(
        select(Document)
        .where(
            Document.statut == StatutDocument.APPROUVE,
            Document.type_document == TypeDocument.COURS,
            Document.cercle_id.is_(None),
        )
        .order_by(Document.titre.asc())
        .limit(200)
    ).all()
    demandes = session.exec(
        select(DemandeMiseAJourCours)
        .order_by(DemandeMiseAJourCours.date_creation.desc())
        .limit(40)
    ).all()
    documents_par_id = {d.id: d for d in documents}
    demandes_vues = []
    for demande in demandes:
        document = documents_par_id.get(demande.document_id) or session.get(
            Document, demande.document_id
        )
        auteur = session.get(Utilisateur, demande.auteur_id)
        demandes_vues.append(
            {"demande": demande, "document": document, "auteur": auteur}
        )
    return templates.TemplateResponse(
        request,
        "harmonisation_enseignant.html",
        {"utilisateur": utilisateur, "documents": documents, "demandes": demandes_vues},
    )


@router.post("/enseignant/harmonisation/documents/{document_id}/demande")
def soumettre_demande_mise_a_jour(
    request: Request,
    document_id: int,
    passage_concerne: str = Form(...),
    contenu_propose: str = Form(...),
    justification: str = Form(...),
    source_justificative: str = Form(...),
    impact_pedagogique: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not professeur_verifie(utilisateur):
        return RedirectResponse("/", status_code=303)
    document = _document_eligible(session, document_id)
    if not document:
        return _rediriger_professeur("document_indisponible")
    passage = passage_concerne.strip()
    proposition = contenu_propose.strip()
    motif = justification.strip()
    source = source_justificative.strip()
    impact = impact_pedagogique.strip()
    if (
        len(passage) < 8
        or len(proposition) < 80
        or len(proposition) > 100000
        or len(motif) < 50
        or len(motif) > 10000
        or len(source) < 8
        or len(source) > 5000
        or len(impact) < 20
        or len(impact) > 5000
    ):
        return _rediriger_professeur("justification_incomplete")
    demande = DemandeMiseAJourCours(
        document_id=document.id,
        auteur_id=utilisateur.id,
        version_source=int(document.version_harmonisee or 0),
        passage_concerne=passage,
        contenu_actuel=document.contenu_harmonise or "",
        contenu_propose=proposition,
        justification=motif,
        source_justificative=source,
        impact_pedagogique=impact,
        statut=StatutDemandeMiseAJourCours.EN_ATTENTE.value,
    )
    session.add(demande)
    session.flush()
    _notifier_enseignants_et_admins(session, demande, document, utilisateur)
    session.commit()
    return RedirectResponse(
        f"/enseignant/harmonisation/demandes/{demande.id}", status_code=303
    )


@router.get("/enseignant/harmonisation/demandes/{demande_id}")
def consulter_demande_professeur(
    request: Request,
    demande_id: int,
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not professeur_verifie(utilisateur):
        return RedirectResponse("/", status_code=303)
    demande = session.get(DemandeMiseAJourCours, demande_id)
    if not demande:
        return _rediriger_professeur("demande_introuvable")
    return templates.TemplateResponse(
        request,
        "harmonisation_detail.html",
        {**_details_demande(session, demande), "utilisateur": utilisateur, "is_admin": False},
    )


@router.post("/enseignant/harmonisation/demandes/{demande_id}/commenter")
def commenter_demande_professeur(
    request: Request,
    demande_id: int,
    message: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not professeur_verifie(utilisateur):
        return RedirectResponse("/", status_code=303)
    demande = session.get(DemandeMiseAJourCours, demande_id)
    if (
        not demande
        or demande.statut
        in {
            StatutDemandeMiseAJourCours.VALIDEE.value,
            StatutDemandeMiseAJourCours.REFUSEE.value,
        }
    ):
        return _rediriger_professeur("discussion_fermee")
    texte = message.strip()
    if len(texte) < 10 or len(texte) > 3000:
        return RedirectResponse(
            f"/enseignant/harmonisation/demandes/{demande_id}?erreur=commentaire_invalide",
            status_code=303,
        )
    _ajouter_echange(session, demande, utilisateur, texte)
    if utilisateur.id != demande.auteur_id:
        _notifications_statut(
            session, demande, session.get(Document, demande.document_id), utilisateur,
            "un enseignant a ajouté un commentaire à ta proposition.",
        )
    session.commit()
    return RedirectResponse(
        f"/enseignant/harmonisation/demandes/{demande_id}", status_code=303
    )


@router.get("/admin/harmonisation-cours")
def page_harmonisation_admin(
    request: Request,
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not administrateur_autorise(utilisateur):
        return RedirectResponse("/", status_code=303)
    demandes = session.exec(
        select(DemandeMiseAJourCours)
        .order_by(DemandeMiseAJourCours.date_creation.desc())
        .limit(100)
    ).all()
    demandes_vues = [
        {
            "demande": d,
            "document": session.get(Document, d.document_id),
            "auteur": session.get(Utilisateur, d.auteur_id),
        }
        for d in demandes
    ]
    return templates.TemplateResponse(
        request,
        "harmonisation_admin.html",
        {"utilisateur": utilisateur, "demandes": demandes_vues},
    )


@router.get("/admin/harmonisation-cours/demandes/{demande_id}")
def consulter_demande_admin(
    request: Request,
    demande_id: int,
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not administrateur_autorise(utilisateur):
        return RedirectResponse("/", status_code=303)
    demande = session.get(DemandeMiseAJourCours, demande_id)
    if not demande:
        return RedirectResponse("/admin/harmonisation-cours", status_code=303)
    return templates.TemplateResponse(
        request,
        "harmonisation_detail.html",
        {**_details_demande(session, demande), "utilisateur": utilisateur, "is_admin": True},
    )


@router.post("/admin/harmonisation-cours/demandes/{demande_id}/commenter")
def commenter_demande_admin(
    request: Request,
    demande_id: int,
    message: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not administrateur_autorise(utilisateur):
        return RedirectResponse("/", status_code=303)
    demande = session.get(DemandeMiseAJourCours, demande_id)
    if (
        not demande
        or demande.statut
        in {
            StatutDemandeMiseAJourCours.VALIDEE.value,
            StatutDemandeMiseAJourCours.REFUSEE.value,
        }
    ):
        return RedirectResponse("/admin/harmonisation-cours", status_code=303)
    texte = message.strip()
    if len(texte) < 10 or len(texte) > 3000:
        return RedirectResponse(
            f"/admin/harmonisation-cours/demandes/{demande_id}?erreur=commentaire_invalide",
            status_code=303,
        )
    _ajouter_echange(session, demande, utilisateur, texte)
    _notifications_statut(
        session, demande, session.get(Document, demande.document_id), utilisateur,
        "l'administrateur a ajouté un commentaire à ta proposition.",
    )
    session.commit()
    return RedirectResponse(
        f"/admin/harmonisation-cours/demandes/{demande_id}", status_code=303
    )


def publier_demande_validee(
    demande: DemandeMiseAJourCours,
    document: Document,
    administrateur: Utilisateur,
    maintenant: Optional[datetime] = None,
) -> bool:
    """Refuse une publication si une version plus récente existe déjà."""
    if (
        document.statut != StatutDocument.APPROUVE
        or document.type_document != TypeDocument.COURS
        or int(document.version_harmonisee or 0) != int(demande.version_source or 0)
    ):
        return False
    maintenant = maintenant or datetime.utcnow()
    document.contenu_harmonise = demande.contenu_propose
    document.version_harmonisee = int(document.version_harmonisee or 0) + 1
    document.date_mise_a_jour_harmonisee = maintenant
    demande.statut = StatutDemandeMiseAJourCours.VALIDEE.value
    demande.traite_par_id = administrateur.id
    demande.date_traitement = maintenant
    demande.date_modification = maintenant
    demande.motif_decision = "Validée et publiée par l'administrateur."
    return True


@router.post("/admin/harmonisation-cours/demandes/{demande_id}/decision")
def traiter_demande_admin(
    request: Request,
    demande_id: int,
    decision: str = Form(...),
    motif_decision: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not administrateur_autorise(utilisateur):
        return RedirectResponse("/", status_code=303)
    demande = session.get(DemandeMiseAJourCours, demande_id)
    if not demande:
        return RedirectResponse("/admin/harmonisation-cours", status_code=303)
    if demande.statut in {
        StatutDemandeMiseAJourCours.VALIDEE.value,
        StatutDemandeMiseAJourCours.REFUSEE.value,
    }:
        return RedirectResponse(
            f"/admin/harmonisation-cours/demandes/{demande_id}?erreur=decision_deja_prise",
            status_code=303,
        )
    motif = motif_decision.strip()
    if len(motif) < 20 or len(motif) > 5000:
        return RedirectResponse(
            f"/admin/harmonisation-cours/demandes/{demande_id}?erreur=motif_decision_invalide",
            status_code=303,
        )
    # Verrouiller la ligne du cours pendant le contrôle de version et la publication.
    document = session.exec(
        select(Document)
        .where(Document.id == demande.document_id)
        .with_for_update()
    ).first()
    if not document:
        return RedirectResponse("/admin/harmonisation-cours?etat=document_introuvable", status_code=303)

    maintenant = datetime.utcnow()
    if decision == "valider":
        if not publier_demande_validee(demande, document, utilisateur, maintenant):
            demande.statut = StatutDemandeMiseAJourCours.PRECISIONS_DEMANDEES.value
            demande.traite_par_id = utilisateur.id
            demande.date_traitement = maintenant
            demande.date_modification = maintenant
            demande.motif_decision = (
                "La version source n'est plus la version publiée. "
                "L'enseignant doit actualiser sa proposition avant une nouvelle validation."
            )
            _ajouter_echange(session, demande, utilisateur, demande.motif_decision)
            session.add(demande)
            _notifications_statut(
                session, demande, document, utilisateur,
                "la proposition doit être actualisée : une version plus récente existe.",
            )
            session.commit()
            return RedirectResponse(
                f"/admin/harmonisation-cours/demandes/{demande_id}?erreur=version_deja_modifiee",
                status_code=303,
            )
        demande.motif_decision = motif
        session.add(document)
        message = (
            f"Ta proposition pour « {document.titre} » a été validée et publiée. "
            f"La bibliothèque affiche maintenant la version {document.version_harmonisee}."
        )
    elif decision == "refuser":
        demande.statut = StatutDemandeMiseAJourCours.REFUSEE.value
        demande.traite_par_id = utilisateur.id
        demande.date_traitement = maintenant
        demande.date_modification = maintenant
        demande.motif_decision = motif
        message = f"Ta proposition pour « {document.titre} » a été refusée. Motif : {motif}"
    elif decision == "demander_precisions":
        demande.statut = StatutDemandeMiseAJourCours.PRECISIONS_DEMANDEES.value
        demande.traite_par_id = utilisateur.id
        demande.date_traitement = maintenant
        demande.date_modification = maintenant
        demande.motif_decision = motif
        _ajouter_echange(
            session, demande, utilisateur,
            f"Précisions demandées par l'administrateur : {motif}",
        )
        message = f"Des précisions sont demandées pour ta proposition sur « {document.titre} »."
    else:
        return RedirectResponse(
            f"/admin/harmonisation-cours/demandes/{demande_id}?erreur=decision_invalide",
            status_code=303,
        )
    session.add(demande)
    _notifications_statut(session, demande, document, utilisateur, message)
    session.commit()
    return RedirectResponse(
        f"/admin/harmonisation-cours/demandes/{demande_id}?etat=decision_enregistree",
        status_code=303,
    )


@router.get("/documents/{document_id}/cours-harmonise")
def consulter_cours_harmonise_public(
    document_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)
    if (
        not document
        or document.statut != StatutDocument.APPROUVE
        or document.type_document != TypeDocument.COURS
        or document.cercle_id is not None
        or not (document.contenu_harmonise or "").strip()
    ):
        return RedirectResponse("/documents", status_code=303)
    return templates.TemplateResponse(
        request,
        "cours_harmonise.html",
        {"utilisateur": utilisateur_courant(request, session), "document": document},
    )
