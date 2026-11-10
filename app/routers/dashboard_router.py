import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..auth import utilisateur_courant
from ..models import Cours, DemandeMiseAJourCours, Document, InscriptionCours, ProgressionNotion, RoleUtilisateur, Utilisateur
from .. import dashboard as dashboard_module
from .. import learning_recap

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/dashboard")
def page_dashboard(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

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
