import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form
from sqlalchemy import func
from fastapi.responses import JSONResponse, RedirectResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..auth import utilisateur_courant
from ..models import Cours, Devoir, DemandeAccompagnement, DemandeMiseAJourCours, Document, InscriptionCours, ProgressionNotion, RenduDevoir, RoleUtilisateur, Seance, StatutSeance, Utilisateur
from .. import dashboard as dashboard_module
from .. import learning_recap

router = APIRouter()

logger = logging.getLogger(__name__)


def donnees_dashboard_enseignant(session: Session, utilisateur: Utilisateur) -> dict:
    """Construit l'espace professionnel uniquement depuis les cours du professeur connecté."""
    cours = session.exec(
        select(Cours)
        .where(Cours.professeur_id == utilisateur.id)
        .order_by(Cours.date_creation.desc())
        .limit(100)
    ).all()
    nb_cours = int(
        session.exec(
            select(func.count(Cours.id)).where(Cours.professeur_id == utilisateur.id)
        ).one() or 0
    )

    if not cours:
        return {
            "statistiques_enseignant": {
                "cours": nb_cours,
                "inscriptions": 0,
                "seances_planifiees": 0,
                "copies_a_corriger": 0,
            },
            "cours_enseignes": [],
        }

    nb_inscriptions = int(
        session.exec(
            select(func.count(InscriptionCours.id))
            .join(Cours, Cours.id == InscriptionCours.cours_id)
            .where(Cours.professeur_id == utilisateur.id)
        ).one() or 0
    )
    nb_seances_planifiees = int(
        session.exec(
            select(func.count(Seance.id))
            .join(Cours, Cours.id == Seance.cours_id)
            .where(
                Cours.professeur_id == utilisateur.id,
                Seance.statut == StatutSeance.PLANIFIEE,
            )
        ).one() or 0
    )
    copies_a_corriger = int(
        session.exec(
            select(func.count(RenduDevoir.id))
            .join(Devoir, Devoir.id == RenduDevoir.devoir_id)
            .join(Cours, Cours.id == Devoir.cours_id)
            .where(
                Cours.professeur_id == utilisateur.id,
                RenduDevoir.note == None,  # noqa: E711
            )
        ).one() or 0
    )

    cours_enseignes = []
    for item in cours:
        inscrits = int(
            session.exec(
                select(func.count(InscriptionCours.id)).where(
                    InscriptionCours.cours_id == item.id
                )
            ).one() or 0
        )
        cours_enseignes.append({"cours": item, "inscrits": inscrits})

    return {
        "statistiques_enseignant": {
            "cours": nb_cours,
            "inscriptions": nb_inscriptions,
            "seances_planifiees": nb_seances_planifiees,
            "copies_a_corriger": copies_a_corriger,
        },
        "cours_enseignes": cours_enseignes,
    }


@router.get("/dashboard")
def page_dashboard(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    if (
        utilisateur.role == RoleUtilisateur.REPETITEUR
        or (
            utilisateur.profil_souhaite == "repetiteur"
            and utilisateur.statut_verification_repetiteur in {"en_attente", "refuse"}
        )
    ):
        demandes_accompagnement = []
        if utilisateur.role == RoleUtilisateur.REPETITEUR and utilisateur.statut_verification_repetiteur == "approuve":
            lignes_demandes = session.exec(
                select(DemandeAccompagnement, Utilisateur)
                .join(Utilisateur, Utilisateur.id == DemandeAccompagnement.etudiant_id)
                .where(DemandeAccompagnement.repetiteur_id == utilisateur.id)
                .order_by(DemandeAccompagnement.date_creation.desc())
                .limit(40)
            ).all()
            for demande, etudiant in lignes_demandes:
                morceaux_nom = [part for part in (etudiant.nom or "").strip().split() if part]
                nom_public = (
                    f"{morceaux_nom[0]} {morceaux_nom[-1][0].upper()}."
                    if len(morceaux_nom) > 1
                    else (morceaux_nom[0] if morceaux_nom else "Élève")
                )
                demandes_accompagnement.append({
                    "demande": demande,
                    "etudiant_nom": nom_public,
                })

        return templates.TemplateResponse(
            request,
            "dashboard_repetiteur.html",
            {
                "utilisateur": utilisateur,
                "statut_repetiteur": getattr(utilisateur, "statut_verification_repetiteur", "non_concerne"),
                "demandes_accompagnement": demandes_accompagnement,
            },
        )

    if utilisateur.role == RoleUtilisateur.PROFESSEUR:
        if utilisateur.statut_verification_enseignant == "approuve":
            donnees_enseignant = donnees_dashboard_enseignant(session, utilisateur)
            return templates.TemplateResponse(
                request,
                "dashboard_enseignant.html",
                {
                    "utilisateur": utilisateur,
                    "statut_enseignant": utilisateur.statut_verification_enseignant,
                    **donnees_enseignant,
                },
            )
        return templates.TemplateResponse(
            request,
            "dashboard_enseignant.html",
            {
                "utilisateur": utilisateur,
                "statut_enseignant": utilisateur.statut_verification_enseignant,
                "statistiques_enseignant": {
                    "cours": 0, "inscriptions": 0,
                    "seances_planifiees": 0, "copies_a_corriger": 0,
                },
                "cours_enseignes": [],
            },
        )

    dashboard_module.notifier_echeances_proches(session, utilisateur.id)
    donnees = dashboard_module.donnees_dashboard(session, utilisateur)

    alertes_harmonisation = None
    if (
        utilisateur.role == RoleUtilisateur.PROFESSEUR
        and utilisateur.statut_verification_enseignant == "approuve"
    ):
        demandes_harmonisation = session.exec(
            select(DemandeMiseAJourCours)
            .order_by(DemandeMiseAJourCours.date_creation.desc())
            .limit(12)
        ).all()
        alertes_harmonisation = []
        for demande in demandes_harmonisation:
            document = session.get(Document, demande.document_id)
            auteur = session.get(Utilisateur, demande.auteur_id)
            if document:
                alertes_harmonisation.append(
                    {"demande": demande, "document": document, "auteur": auteur}
                )

    return templates.TemplateResponse(
        request,
        "dashboard_etudiant.html",
        {"utilisateur": utilisateur, **donnees, "alertes_harmonisation": alertes_harmonisation},
    )



@router.post("/repetiteur/profil")
def enregistrer_profil_repetiteur(
    request: Request,
    matieres: str = Form(""),
    niveaux: str = Form(""),
    tarif_horaire: str = Form(""),
    presentation: str = Form(""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Met à jour la fiche professionnelle uniquement après validation admin."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.REPETITEUR:
        return RedirectResponse("/dashboard", status_code=303)
    if utilisateur.statut_verification_repetiteur != "approuve":
        return RedirectResponse("/dashboard?erreur=profil_non_valide", status_code=303)

    matieres = (matieres or "").strip()
    niveaux = (niveaux or "").strip()
    presentation = (presentation or "").strip()
    tarif_nettoye = (tarif_horaire or "").strip()
    tarif = None
    if tarif_nettoye:
        try:
            tarif = int(tarif_nettoye)
        except (TypeError, ValueError):
            return RedirectResponse("/dashboard?erreur=tarif_invalide", status_code=303)
        if tarif < 1 or tarif > 10000000:
            return RedirectResponse("/dashboard?erreur=tarif_invalide", status_code=303)
    if len(matieres) > 500 or len(niveaux) > 500 or len(presentation) > 1000:
        return RedirectResponse("/dashboard?erreur=profil_trop_long", status_code=303)

    utilisateur.matieres_repetiteur = matieres or None
    utilisateur.niveaux_repetiteur = niveaux or None
    utilisateur.tarif_horaire_repetiteur_ariary = tarif
    utilisateur.bio = presentation or None
    session.add(utilisateur)
    session.commit()
    return RedirectResponse("/dashboard?ok=profil_enregistre", status_code=303)



@router.get("/api/apprentissage/bilan-reprise")
def api_bilan_reprise(
    request: Request,
    depuis: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """Retourne le bilan privé de l'utilisateur authentifié, sans modifier sa progression."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return JSONResponse(
            {"erreur": "connexion_requise"},
            status_code=401,
            headers={"Cache-Control": "no-store"},
        )
    if utilisateur.role != RoleUtilisateur.ETUDIANT:
        return JSONResponse(
            {"erreur": "espace_reserve_aux_apprenants"},
            status_code=403,
            headers={"Cache-Control": "no-store"},
        )

    try:
        bilan = learning_recap.construire_bilan(session, utilisateur, depuis=depuis)
    except Exception:
        # Pas de détail interne, contenu d'apprentissage ou prompt dans la réponse HTTP.
        logger.exception("Échec du bilan de reprise pour utilisateur_id=%s", utilisateur.id)
        return JSONResponse(
            {"erreur": "bilan_indisponible"},
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )

    return JSONResponse(bilan, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})

 
@router.get("/mon-parcours")
def page_mon_parcours(request: Request, session: Session = Depends(get_session)):
    """Vue personnelle de progression, construite depuis les traces du compte connecté."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    if utilisateur.role != RoleUtilisateur.ETUDIANT:
        return RedirectResponse("/dashboard", status_code=303)

    maintenant = datetime.utcnow()
    bilan = learning_recap.construire_bilan(
        session, utilisateur,
        depuis=(maintenant - timedelta(days=30)).isoformat(),
        maintenant=maintenant,
    )
    progressions = session.exec(
        select(ProgressionNotion)
        .where(
            ProgressionNotion.utilisateur_id == utilisateur.id,
            ProgressionNotion.nb_questions > 0,
        )
        .order_by(ProgressionNotion.score_maitrise.asc(), ProgressionNotion.date_maj.desc())
        .limit(250)
    ).all()

    notions = []
    for progression in progressions:
        diagnostic = learning_recap._statut_progression(progression)
        prochaine = progression.prochaine_revision_le
        notions.append({
            "matiere": str(progression.matiere or "Matière non précisée")[:120],
            "notion": str(progression.notion or "Notion")[:160],
            "score": diagnostic["score"],
            "libelle": diagnostic["libelle"],
            "maitrise_confirmee": diagnostic["maitrise_confirmee"],
            "questions": max(0, int(progression.nb_questions or 0)),
            "erreurs": max(0, int(progression.nb_erreurs or 0)),
            "prochaine_revision": prochaine,
            "revision_due": bool(prochaine and prochaine <= maintenant),
        })

    notions_confirmees = sum(1 for n in notions if n["maitrise_confirmee"])
    score_global = round(sum(n["score"] for n in notions) / len(notions)) if notions else None
    a_renforcer = [
        n for n in notions
        if not n["maitrise_confirmee"] and (
            n["score"] < 70 or n["erreurs"] >= 2 or n["revision_due"]
        )
    ][:8]
    revisions = sorted(
        [n for n in notions if n["prochaine_revision"] is not None],
        key=lambda n: (not n["revision_due"], n["prochaine_revision"]),
    )[:8]

    inscriptions = session.exec(
        select(InscriptionCours)
        .where(InscriptionCours.utilisateur_id == utilisateur.id)
        .order_by(InscriptionCours.date_inscription.desc())
    ).all()
    cours_ids = sorted({i.cours_id for i in inscriptions})
    cours_par_id = {
        cours.id: cours
        for cours in session.exec(select(Cours).where(Cours.id.in_(cours_ids))).all()
    } if cours_ids else {}
    cours_suivis = [
        {"cours": cours_par_id[i.cours_id], "date_inscription": i.date_inscription}
        for i in inscriptions if i.cours_id in cours_par_id
    ]

    return templates.TemplateResponse(
        request,
        "mon_parcours.html",
        {
            "utilisateur": utilisateur,
            "bilan": bilan,
            "notions": notions,
            "notions_confirmees": notions_confirmees,
            "score_global": score_global,
            "a_renforcer": a_renforcer,
            "revisions": revisions,
            "cours_suivis": cours_suivis,
        },
    )
