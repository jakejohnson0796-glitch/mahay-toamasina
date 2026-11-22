"""Espace indépendant d'harmonisation réservé aux enseignants vérifiés.

Les enseignants proposent et commentent les évolutions des cours. Seul un
administrateur peut accepter, refuser ou demander des précisions. Une version
acceptée est publiée directement sur la fiche du document dans la bibliothèque.
"""
from datetime import datetime
import json
from typing import Optional
from urllib.parse import urlsplit

from sqlalchemy.exc import IntegrityError

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..auth import utilisateur_courant
from ..config import parametres
from ..csrf import verifier_csrf
from ..database import get_session
from ..models import (
    AnalyseComparativeLecon,
    ContributionLecon,
    DemandeMiseAJourCours,
    LeconReferentielle,
    MatiereScolaire,
    NiveauScolaire,
    OptionScolaire,
    ProgrammeMatiereScolaire,
    ReferentielScolaire,
    StatutLeconReferentielle,
    VersionCoursHarmoniseLecon,
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
    utilisateur = utilisateur_courant(request, session)
    if not (professeur_verifie(utilisateur) or administrateur_autorise(utilisateur)):
        return RedirectResponse("/", status_code=303)

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
        {"utilisateur": utilisateur, "document": document},
    )


# ---------------------------------------------------------------------------
# Référentiel national des leçons : contributions multi-sources et publication
# ---------------------------------------------------------------------------

def _programme_lecon(session: Session, programme_id: int) -> Optional[dict]:
    programme = session.get(ProgrammeMatiereScolaire, programme_id)
    if not programme or programme.statut_validation != "verifie":
        return None
    referentiel = session.get(ReferentielScolaire, programme.referentiel_id)
    niveau = session.get(NiveauScolaire, programme.niveau_id)
    matiere = session.get(MatiereScolaire, programme.matiere_id)
    option = session.get(OptionScolaire, programme.option_id) if programme.option_id else None
    if not referentiel or not niveau or not matiere:
        return None
    if not niveau.est_actif or niveau.statut_validation != "verifie":
        return None
    if not matiere.est_active or matiere.statut_validation != "verifie":
        return None
    if option and (not option.est_active or option.statut_validation != "verifie"):
        return None
    return {
        "programme": programme,
        "referentiel": referentiel,
        "niveau": niveau,
        "matiere": matiere,
        "option": option,
    }


def _contexte_liste_lecon(session: Session, lecon: LeconReferentielle) -> dict:
    scope = _programme_lecon(session, lecon.programme_matiere_id)
    return {
        "lecon": lecon,
        "scope": scope,
    }


def _url_source_officielle_valide(valeur: str) -> bool:
    try:
        morceaux = urlsplit((valeur or "").strip())
    except ValueError:
        return False
    return (
        morceaux.scheme == "https"
        and bool(morceaux.netloc)
        and " " not in morceaux.netloc
        and len(valeur.strip()) <= 1200
    )


def _notifier_contribution_lecon(
    session: Session,
    lecon: LeconReferentielle,
    contribution: ContributionLecon,
    auteur: Utilisateur,
) -> None:
    destination_admin = f"/admin/harmonisation-nationale/lecons/{lecon.id}"
    destination_enseignant = f"/enseignant/harmonisation/lecons/{lecon.id}"
    admins = session.exec(
        select(Utilisateur).where(Utilisateur.role == RoleUtilisateur.ADMIN)
    ).all()
    enseignants = session.exec(
        select(Utilisateur).where(
            Utilisateur.role == RoleUtilisateur.PROFESSEUR,
            Utilisateur.statut_verification_enseignant == "approuve",
        )
    ).all()
    resume = (
        f"Nouvelle contribution pour « {lecon.titre} » de {auteur.nom}. "
        f"Source : {contribution.source_reference[:180]}"
    )
    destinataires = {}
    for compte in admins:
        destinataires[compte.id] = (compte, destination_admin)
    for compte in enseignants:
        if compte.id != auteur.id:
            destinataires[compte.id] = (compte, destination_enseignant)
    for compte, url in destinataires.values():
        _notifier(session, compte, auteur.id, resume, url)


def _detail_lecon(session: Session, lecon: LeconReferentielle, administrateur: bool) -> dict:
    scope = _programme_lecon(session, lecon.programme_matiere_id)
    requete = select(ContributionLecon).where(
        ContributionLecon.lecon_id == lecon.id
    )
    if not administrateur:
        requete = requete.where(ContributionLecon.statut.in_(["soumise", "retenue"]))
    contributions = session.exec(
        requete.order_by(ContributionLecon.date_creation.desc()).limit(100)
    ).all()
    auteurs = {}
    auteurs_ids = {item.auteur_id for item in contributions}
    if auteurs_ids:
        auteurs = {
            compte.id: compte
            for compte in session.exec(
                select(Utilisateur).where(Utilisateur.id.in_(auteurs_ids))
            ).all()
        }
    analyses = session.exec(
        select(AnalyseComparativeLecon)
        .where(AnalyseComparativeLecon.lecon_id == lecon.id)
        .order_by(AnalyseComparativeLecon.date_creation.desc())
        .limit(10)
    ).all() if administrateur else []
    resultats_analyses = []
    for analyse in analyses:
        try:
            resultat = json.loads(analyse.resultat_json or "{}")
        except (TypeError, ValueError):
            resultat = {"avertissement": "Résultat d'analyse illisible."}
        resultats_analyses.append({"analyse": analyse, "resultat": resultat})
    versions = session.exec(
        select(VersionCoursHarmoniseLecon)
        .where(VersionCoursHarmoniseLecon.lecon_id == lecon.id)
        .order_by(VersionCoursHarmoniseLecon.numero_version.desc())
        .limit(30)
    ).all() if administrateur else []
    return {
        "lecon": lecon,
        "scope": scope,
        "contributions": [
            {"contribution": item, "auteur": auteurs.get(item.auteur_id)}
            for item in contributions
        ],
        "analyses": resultats_analyses,
        "versions": versions,
    }


@router.get("/admin/harmonisation-nationale")
def espace_national_lecons_admin(
    request: Request,
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not administrateur_autorise(utilisateur):
        return RedirectResponse("/", status_code=303)
    programmes_bruts = session.exec(
        select(ProgrammeMatiereScolaire)
        .where(ProgrammeMatiereScolaire.statut_validation == "verifie")
        .order_by(ProgrammeMatiereScolaire.id.desc())
        .limit(500)
    ).all()
    programmes = [
        {"programme": item, "scope": _programme_lecon(session, item.id)}
        for item in programmes_bruts
    ]
    programmes = [item for item in programmes if item["scope"]]
    lecons = session.exec(
        select(LeconReferentielle)
        .order_by(LeconReferentielle.date_creation.desc())
        .limit(200)
    ).all()
    demandes = [_contexte_liste_lecon(session, item) for item in lecons]
    return templates.TemplateResponse(
        request,
        "harmonisation_referentiel_admin.html",
        {
            "utilisateur": utilisateur,
            "programmes": programmes,
            "lecons": demandes,
        },
    )


@router.post("/admin/harmonisation-nationale/lecons")
def creer_lecon_referentielle(
    request: Request,
    programme_matiere_id: int = Form(...),
    code: str = Form(...),
    chapitre: str = Form(""),
    titre: str = Form(...),
    objectifs_pedagogiques: str = Form(""),
    source_officielle: str = Form(...),
    reference_source: str = Form(""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not administrateur_autorise(utilisateur):
        return RedirectResponse("/", status_code=303)
    scope = _programme_lecon(session, programme_matiere_id)
    code, titre = code.strip(), titre.strip()
    source = source_officielle.strip()
    if (
        not scope
        or not code
        or len(code) > 40
        or not titre
        or len(titre) > 240
        or len(chapitre.strip()) > 200
        or len(objectifs_pedagogiques.strip()) > 5000
        or not _url_source_officielle_valide(source)
        or len(reference_source.strip()) > 1000
    ):
        return RedirectResponse(
            "/admin/harmonisation-nationale?erreur=lecon_invalide",
            status_code=303,
        )
    lecon = LeconReferentielle(
        programme_matiere_id=programme_matiere_id,
        code=code,
        chapitre=chapitre.strip(),
        titre=titre,
        objectifs_pedagogiques=objectifs_pedagogiques.strip(),
        source_officielle=source,
        reference_source=reference_source.strip(),
        statut_validation=StatutLeconReferentielle.A_VERIFIER.value,
        cree_par_id=utilisateur.id,
    )
    session.add(lecon)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return RedirectResponse(
            "/admin/harmonisation-nationale?erreur=lecon_deja_presente",
            status_code=303,
        )
    session.refresh(lecon)
    return RedirectResponse(
        f"/admin/harmonisation-nationale/lecons/{lecon.id}?etat=lecon_creee",
        status_code=303,
    )


@router.post("/admin/harmonisation-nationale/lecons/{lecon_id}/verifier")
def verifier_lecon_referentielle(
    request: Request,
    lecon_id: int,
    motif_verification: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not administrateur_autorise(utilisateur):
        return RedirectResponse("/", status_code=303)
    lecon = session.get(LeconReferentielle, lecon_id)
    motif = motif_verification.strip()
    if not lecon:
        return RedirectResponse("/admin/harmonisation-nationale", status_code=303)
    if (
        lecon.statut_validation == StatutLeconReferentielle.ARCHIVEE.value
        or not _programme_lecon(session, lecon.programme_matiere_id)
        or not _url_source_officielle_valide(lecon.source_officielle)
        or len(motif) < 20
        or len(motif) > 2000
    ):
        return RedirectResponse(
            f"/admin/harmonisation-nationale/lecons/{lecon.id}?erreur=verification_invalide",
            status_code=303,
        )
    lecon.statut_validation = StatutLeconReferentielle.VERIFIEE.value
    lecon.valide_par_id = utilisateur.id
    lecon.date_validation = datetime.utcnow()
    lecon.motif_validation = motif
    session.add(lecon)
    session.commit()
    return RedirectResponse(
        f"/admin/harmonisation-nationale/lecons/{lecon.id}?etat=lecon_verifiee",
        status_code=303,
    )


@router.get("/enseignant/harmonisation/lecons")
def espace_national_lecons_enseignant(
    request: Request,
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not professeur_verifie(utilisateur):
        return RedirectResponse("/", status_code=303)
    lecons = session.exec(
        select(LeconReferentielle)
        .where(
            LeconReferentielle.statut_validation == StatutLeconReferentielle.VERIFIEE.value,
            LeconReferentielle.statut_publication == "non_publie",
        )
        .order_by(LeconReferentielle.titre)
        .limit(200)
    ).all()
    items = [_contexte_liste_lecon(session, item) for item in lecons]
    return templates.TemplateResponse(
        request,
        "harmonisation_referentiel_enseignant.html",
        {"utilisateur": utilisateur, "lecons": items},
    )


@router.get("/admin/harmonisation-nationale/lecons/{lecon_id}")
def detail_lecon_nationale_admin(
    request: Request,
    lecon_id: int,
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not administrateur_autorise(utilisateur):
        return RedirectResponse("/", status_code=303)
    lecon = session.get(LeconReferentielle, lecon_id)
    if not lecon:
        return RedirectResponse("/admin/harmonisation-nationale", status_code=303)
    return templates.TemplateResponse(
        request,
        "harmonisation_lecon_detail.html",
        {
            **_detail_lecon(session, lecon, True),
            "utilisateur": utilisateur,
            "is_admin": True,
        },
    )


@router.get("/enseignant/harmonisation/lecons/{lecon_id}")
def detail_lecon_nationale_enseignant(
    request: Request,
    lecon_id: int,
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not professeur_verifie(utilisateur):
        return RedirectResponse("/", status_code=303)
    lecon = session.get(LeconReferentielle, lecon_id)
    if (
        not lecon
        or lecon.statut_validation != StatutLeconReferentielle.VERIFIEE.value
    ):
        return RedirectResponse("/enseignant/harmonisation/lecons", status_code=303)
    return templates.TemplateResponse(
        request,
        "harmonisation_lecon_detail.html",
        {
            **_detail_lecon(session, lecon, False),
            "utilisateur": utilisateur,
            "is_admin": False,
        },
    )


@router.post("/enseignant/harmonisation/lecons/{lecon_id}/contributions")
def soumettre_contribution_lecon(
    request: Request,
    lecon_id: int,
    titre: str = Form(...),
    contenu: str = Form(...),
    source_reference: str = Form(...),
    justification: str = Form(...),
    impact_pedagogique: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not professeur_verifie(utilisateur):
        return RedirectResponse("/", status_code=303)
    lecon = session.get(LeconReferentielle, lecon_id)
    if (
        not lecon
        or lecon.statut_validation != StatutLeconReferentielle.VERIFIEE.value
        or not _programme_lecon(session, lecon.programme_matiere_id)
    ):
        return RedirectResponse("/enseignant/harmonisation/lecons", status_code=303)
    titre, texte = titre.strip(), contenu.strip()
    source, motif, impact = (
        source_reference.strip(),
        justification.strip(),
        impact_pedagogique.strip(),
    )
    if (
        not titre or len(titre) > 180
        or len(texte) < 100 or len(texte) > 12000
        or len(source) < 8 or len(source) > 2000
        or len(motif) < 50 or len(motif) > 5000
        or len(impact) < 20 or len(impact) > 3000
    ):
        return RedirectResponse(
            f"/enseignant/harmonisation/lecons/{lecon_id}?erreur=contribution_invalide",
            status_code=303,
        )
    contribution = ContributionLecon(
        lecon_id=lecon.id,
        auteur_id=utilisateur.id,
        titre=titre,
        contenu=texte,
        source_reference=source,
        justification=motif,
        impact_pedagogique=impact,
    )
    session.add(contribution)
    session.flush()
    _notifier_contribution_lecon(session, lecon, contribution, utilisateur)
    session.commit()
    return RedirectResponse(
        f"/enseignant/harmonisation/lecons/{lecon_id}?etat=contribution_envoyee",
        status_code=303,
    )


@router.post("/admin/harmonisation-nationale/lecons/{lecon_id}/analyser")
def lancer_analyse_comparative_lecon(
    request: Request,
    lecon_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not administrateur_autorise(utilisateur):
        return RedirectResponse("/", status_code=303)
    if not parametres.groq_api_key or not parametres.groq_model:
        return RedirectResponse(
            f"/admin/harmonisation-nationale/lecons/{lecon_id}?erreur=ia_non_configuree",
            status_code=303,
        )
    lecon = session.get(LeconReferentielle, lecon_id)
    if (
        not lecon
        or lecon.statut_validation != StatutLeconReferentielle.VERIFIEE.value
        or not _programme_lecon(session, lecon.programme_matiere_id)
    ):
        return RedirectResponse("/admin/harmonisation-nationale", status_code=303)
    contributions = session.exec(
        select(ContributionLecon)
        .where(
            ContributionLecon.lecon_id == lecon.id,
            ContributionLecon.statut.in_(["soumise", "retenue"]),
        )
        .order_by(ContributionLecon.date_creation.desc())
        .limit(50)
    ).all()
    selection = []
    auteurs = set()
    for contribution in contributions:
        if contribution.auteur_id in auteurs:
            continue
        selection.append(contribution)
        auteurs.add(contribution.auteur_id)
        if len(selection) >= 5:
            break
    if len(selection) < 2:
        return RedirectResponse(
            f"/admin/harmonisation-nationale/lecons/{lecon_id}?erreur=deux_enseignants_requis",
            status_code=303,
        )
    analyse = AnalyseComparativeLecon(
        lecon_id=lecon.id,
        contributions_ids_json=json.dumps([item.id for item in selection]),
        resultat_json="{}",
        modele=str(parametres.groq_model)[:120],
        statut="en_attente",
        cree_par_id=utilisateur.id,
    )
    session.add(analyse)
    session.commit()
    session.refresh(analyse)
    from .. import ai_queue

    tache_id = ai_queue.planifier_analyse_comparative_lecon(analyse.id)
    if tache_id is None:
        analyse.statut = "a_revoir"
        analyse.resultat_json = json.dumps(
            {"erreur": "La tâche n'a pas pu être enregistrée dans la file IA."},
            ensure_ascii=False,
        )
        session.add(analyse)
        session.commit()
        return RedirectResponse(
            f"/admin/harmonisation-nationale/lecons/{lecon_id}?erreur=analyse_non_planifiee",
            status_code=303,
        )
    return RedirectResponse(
        f"/admin/harmonisation-nationale/lecons/{lecon_id}?etat=analyse_planifiee",
        status_code=303,
    )


@router.post("/admin/harmonisation-nationale/lecons/{lecon_id}/contributions/{contribution_id}/decision")
def traiter_contribution_lecon(
    request: Request,
    lecon_id: int,
    contribution_id: int,
    decision: str = Form(...),
    motif_decision: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not administrateur_autorise(utilisateur):
        return RedirectResponse("/", status_code=303)
    contribution = session.get(ContributionLecon, contribution_id)
    motif = motif_decision.strip()
    if (
        not contribution
        or contribution.lecon_id != lecon_id
        or contribution.statut not in {"soumise", "retenue"}
        or decision not in {"retenue", "refusee"}
        or len(motif) < 20
        or len(motif) > 3000
    ):
        return RedirectResponse(
            f"/admin/harmonisation-nationale/lecons/{lecon_id}?erreur=decision_invalide",
            status_code=303,
        )
    contribution.statut = decision
    contribution.traite_par_id = utilisateur.id
    contribution.date_traitement = datetime.utcnow()
    contribution.motif_decision = motif
    session.add(contribution)
    auteur = session.get(Utilisateur, contribution.auteur_id)
    if auteur:
        _notifier(
            session,
            auteur,
            utilisateur.id,
            f"Ta contribution pour « {lecon_id} » a été {decision}. Motif : {motif}",
            f"/enseignant/harmonisation/lecons/{lecon_id}",
        )
    session.commit()
    return RedirectResponse(
        f"/admin/harmonisation-nationale/lecons/{lecon_id}?etat=decision_enregistree",
        status_code=303,
    )


def publier_version_lecon_harmonisee(
    lecon: LeconReferentielle,
    analyse: AnalyseComparativeLecon,
    contributions: list[ContributionLecon],
    administrateur: Utilisateur,
    contenu_final: str,
    motif_validation: str,
    maintenant: Optional[datetime] = None,
) -> Optional[VersionCoursHarmoniseLecon]:
    """Crée une version immuable uniquement après validation administrative."""
    if (
        lecon.statut_validation != StatutLeconReferentielle.VERIFIEE.value
        or analyse.lecon_id != lecon.id
        or analyse.statut != "terminee"
    ):
        return None
    try:
        ids_analyse = {int(value) for value in json.loads(analyse.contributions_ids_json or "[]")}
    except (TypeError, ValueError):
        return None
    retenues = [
        item for item in contributions
        if item.id in ids_analyse
        and item.lecon_id == lecon.id
        and item.statut == "retenue"
    ]
    if len({item.auteur_id for item in retenues}) < 2:
        return None
    texte = (contenu_final or "").strip()
    motif = (motif_validation or "").strip()
    if len(texte) < 100 or len(texte) > 100000 or len(motif) < 20 or len(motif) > 3000:
        return None
    maintenant = maintenant or datetime.utcnow()
    numero = int(lecon.version_publiee or 0) + 1
    version = VersionCoursHarmoniseLecon(
        lecon_id=lecon.id,
        numero_version=numero,
        contenu=texte,
        analyse_id=analyse.id,
        contributions_ids_json=json.dumps(sorted(item.id for item in retenues)),
        publie_par_id=administrateur.id,
        motif_validation=motif,
        date_publication=maintenant,
    )
    lecon.contenu_publie = texte
    lecon.version_publiee = numero
    lecon.statut_publication = "publie"
    lecon.date_publication = maintenant
    lecon.publie_par_id = administrateur.id
    return version


@router.post("/admin/harmonisation-nationale/lecons/{lecon_id}/publier")
def publier_lecon_nationale(
    request: Request,
    lecon_id: int,
    analyse_id: int = Form(...),
    contenu_final: str = Form(...),
    motif_validation: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not administrateur_autorise(utilisateur):
        return RedirectResponse("/", status_code=303)
    lecon = session.exec(
        select(LeconReferentielle)
        .where(LeconReferentielle.id == lecon_id)
        .with_for_update()
    ).first()
    analyse = session.get(AnalyseComparativeLecon, analyse_id)
    if not lecon or not analyse or analyse.lecon_id != lecon_id:
        return RedirectResponse("/admin/harmonisation-nationale", status_code=303)
    try:
        ids = [int(value) for value in json.loads(analyse.contributions_ids_json or "[]")]
    except (TypeError, ValueError):
        ids = []
    contributions = session.exec(
        select(ContributionLecon).where(
            ContributionLecon.lecon_id == lecon_id,
            ContributionLecon.id.in_(ids or [-1]),
        )
    ).all()
    version = publier_version_lecon_harmonisee(
        lecon,
        analyse,
        contributions,
        utilisateur,
        contenu_final,
        motif_validation,
    )
    if version is None:
        return RedirectResponse(
            f"/admin/harmonisation-nationale/lecons/{lecon_id}?erreur=publication_refusee",
            status_code=303,
        )
    session.add(version)
    session.add(lecon)
    session.commit()
    return RedirectResponse(
        f"/documents/cours-harmonises/{lecon_id}?etat=publication_reussie",
        status_code=303,
    )


@router.get("/documents/cours-harmonises/{lecon_id}")
def consulter_cours_harmonise_national(
    request: Request,
    lecon_id: int,
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    lecon = session.get(LeconReferentielle, lecon_id)
    if (
        not lecon
        or lecon.statut_validation != StatutLeconReferentielle.VERIFIEE.value
        or lecon.statut_publication != "publie"
        or not (lecon.contenu_publie or "").strip()
    ):
        return RedirectResponse("/documents", status_code=303)
    scope = _programme_lecon(session, lecon.programme_matiere_id)
    versions = session.exec(
        select(VersionCoursHarmoniseLecon)
        .where(VersionCoursHarmoniseLecon.lecon_id == lecon_id)
        .order_by(VersionCoursHarmoniseLecon.numero_version.desc())
        .limit(20)
    ).all()
    return templates.TemplateResponse(
        request,
        "cours_harmonise_national.html",
        {
            "utilisateur": utilisateur,
            "lecon": lecon,
            "scope": scope,
            "versions": versions,
        },
    )
