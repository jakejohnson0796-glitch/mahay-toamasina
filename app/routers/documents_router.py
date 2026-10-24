"""
Coeur de l'application : consulter, deposer, telecharger des documents,
et les valider (moderation) avant qu'ils soient publics.
"""
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime
import json
from typing import Optional
from urllib.parse import urlencode
import mimetypes
import secrets
import tempfile

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse, Response
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..models import (Document, Filiere, NiveauScolaire, OptionScolaire, EtablissementScolaire, ReferentielScolaire, TypeDocument, StatutDocument, RoleUtilisateur, ConsultationDocument, CercleEtude, MembreCercle, Utilisateur, Notification, TypeNotification, TentativeQuiz, TacheIA, FicheRevisionDocument, StatutFicheRevisionDocument)
from ..auth import utilisateur_courant
from ..ai_quiz import generer_quiz_depuis_texte
from ..text_extraction import extraire_texte
from ..storage import sauvegarder_fichier, obtenir_url_telechargement, ouvrir_fichier_local, stockage_distant_actif, FichierInvalide, supprimer_fichier
from ..dependencies import acces_ia_ou_redirection, acces_premium_ou_redirection
from ..web_utils import entier_ou_none
from .. import gamification
from .. import ai_queue
from .. import course_revision
from .. import quiz as quiz_module
from ..rate_limit import limite_depassee
from ..document_classifier import classifier_document
from ..quiz_validation import QuizValidationError, valider_questions

router = APIRouter()


def _est_membre_cercle(session: Session, cercle_id: int, utilisateur_id: int) -> bool:
    """Meme verification que cercles_router._est_membre : reimplementee ici
    (plutot qu'importee) pour ne pas creer de dependance croisee entre les
    deux routers."""
    return (
        session.exec(
            select(MembreCercle).where(
                MembreCercle.cercle_id == cercle_id,
                MembreCercle.utilisateur_id == utilisateur_id,
            )
        ).first()
        is not None
    )


def _charger_fiche_pedagogique_json(contenu: str) -> dict:
    """Charge sans risque les informations détaillées d’une fiche IA."""
    try:
        fiche = json.loads(contenu or "{}")
        return fiche if isinstance(fiche, dict) else {}
    except (TypeError, ValueError):
        return {}


def _charger_fiche_pedagogique(document: Document) -> dict:
    return _charger_fiche_pedagogique_json(document.fiche_pedagogique_json)


def _fiche_pedagogique_peut_etre_validee(document: Document) -> bool:
    statut = str(getattr(document, "resume_statut_ia", "") or "")
    resume = str(getattr(document, "resume_ia", "") or "").strip()
    return bool(resume) and statut in {"generee", "provisoire"}


def _fiche_pedagogique_est_validee(document: Document) -> bool:
    return str(getattr(document, "fiche_validation_statut", "a_verifier") or "a_verifier") == "validee"


def generer_reference(filiere: Optional[Filiere], annee: int, session: Session) -> str:
    """Référence unique commune aux cibles universitaires et scolaires."""
    nom_cible = filiere.nom.upper() if filiere else "SCO"
    prefixe = "".join(c for c in nom_cible if c.isalpha())[:3] or "DOC"
    jeton = secrets.token_hex(4).upper()
    return f"MG-{prefixe}-{annee}-{jeton}"


def _notifier_admins_nouveau_document(session: Session, document: Document, uploader: Utilisateur) -> int:
    """Alerte chaque admin lorsqu'un document entre en moderation."""
    administrateurs = session.exec(
        select(Utilisateur).where(Utilisateur.role == RoleUtilisateur.ADMIN)
    ).all()
    total = 0
    for administrateur in administrateurs:
        if administrateur.id == uploader.id:
            continue
        session.add(
            Notification(
                destinataire_id=administrateur.id,
                type_notification=TypeNotification.NOUVEAU_DOCUMENT,
                contenu=(
                    f"Nouveau document à modérer : {document.titre} "
                    f"({document.reference}), déposé par {uploader.nom}."
                ),
                acteur_id=uploader.id,
            )
        )
        total += 1
    return total


def _notifier_uploader_document(
    session: Session,
    document: Document,
    type_notification: TypeNotification,
    contenu: str,
    acteur_id: Optional[int] = None,
) -> None:
    """Informe l'auteur du résultat de la modération de son document."""
    if not document.uploader_id:
        return
    if acteur_id is not None and document.uploader_id == acteur_id:
        return
    session.add(
        Notification(
            destinataire_id=document.uploader_id,
            type_notification=type_notification,
            contenu=contenu,
            acteur_id=acteur_id,
        )
    )


@router.get("/documents")
def liste_documents(
    request: Request,
    filiere_id: Optional[str] = None,
    matiere: Optional[str] = None,
    type_document: Optional[TypeDocument] = None,
    cercle_id: Optional[int] = None,
    portee_academique: Optional[str] = None,
    niveau_scolaire_id: Optional[int] = None,
    option_scolaire_id: Optional[int] = None,
    etablissement_scolaire_id: Optional[int] = None,
    session: Session = Depends(get_session),
):
    filiere_id = entier_ou_none(filiere_id)
    utilisateur = utilisateur_courant(request, session)
    cercle = None
    if cercle_id is not None:
        # Vue "Documents du cercle" : reservee aux membres, comme le salon
        # de discussion. Un document non-approuve reste invisible ici
        # aussi (meme garantie de moderation que la bibliotheque generale).
        if not utilisateur or not _est_membre_cercle(session, cercle_id, utilisateur.id):
            return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)
        cercle = session.get(CercleEtude, cercle_id)
        if not cercle:
            return RedirectResponse("/cercles", status_code=303)

    requete = select(Document).where(Document.statut == StatutDocument.APPROUVE)
    if cercle_id is not None:
        requete = requete.where(Document.cercle_id == cercle_id)
    elif not utilisateur:
        # Une ressource de cercle reste privée, même si son document est approuvé.
        requete = requete.where(Document.cercle_id.is_(None))
    else:
        cercles_autorises = session.exec(
            select(MembreCercle.cercle_id).where(MembreCercle.utilisateur_id == utilisateur.id)
        ).all()
        requete = requete.where(
            (Document.cercle_id.is_(None)) | (Document.cercle_id.in_(cercles_autorises))
        )
    if portee_academique in {"universitaire", "scolaire"}:
        requete = requete.where(Document.portee_academique == portee_academique)
    if niveau_scolaire_id is not None:
        requete = requete.where(Document.niveau_scolaire_id == niveau_scolaire_id)
    if option_scolaire_id is not None:
        requete = requete.where(Document.option_scolaire_id == option_scolaire_id)
    if etablissement_scolaire_id is not None:
        requete = requete.where(Document.etablissement_scolaire_id == etablissement_scolaire_id)
    if filiere_id:
        requete = requete.where(Document.filiere_id == filiere_id)
    if matiere:
        requete = requete.where(Document.matiere.contains(matiere))
    if type_document:
        requete = requete.where(Document.type_document == type_document)
    documents = session.exec(requete.order_by(Document.date_upload.desc())).all()
    filieres = session.exec(select(Filiere)).all()
    referentiels_scolaires = session.exec(
        select(ReferentielScolaire).order_by(
            ReferentielScolaire.date_creation.desc(),
            ReferentielScolaire.id.desc(),
        )
    ).all()
    referentiel_scolaire_courant = referentiels_scolaires[0] if referentiels_scolaires else None
    if referentiel_scolaire_courant:
        niveaux_scolaires = session.exec(
            select(NiveauScolaire)
            .where(
                NiveauScolaire.referentiel_id == referentiel_scolaire_courant.id,
                NiveauScolaire.est_actif == True,  # noqa: E712
                NiveauScolaire.statut_validation == "verifie",
            )
            .order_by(NiveauScolaire.ordre)
        ).all()
        options_scolaires = session.exec(
            select(OptionScolaire)
            .where(
                OptionScolaire.referentiel_id == referentiel_scolaire_courant.id,
                OptionScolaire.est_active == True,  # noqa: E712
                OptionScolaire.statut_validation == "verifie",
            )
            .order_by(OptionScolaire.libelle)
        ).all()
    else:
        niveaux_scolaires = []
        options_scolaires = []
    etablissements_scolaires = session.exec(
        select(EtablissementScolaire)
        .where(
            EtablissementScolaire.est_actif == True,  # noqa: E712
            EtablissementScolaire.est_verifie == True,  # noqa: E712
        )
        .order_by(EtablissementScolaire.nom)
        .limit(200)
    ).all()

    # Les dépôts non encore publics ne sont visibles qu’à leur déposant.
    mes_depots = []
    if utilisateur:
        requete_depots = select(Document).where(
            Document.uploader_id == utilisateur.id,
            Document.statut.in_([StatutDocument.EN_ATTENTE, StatutDocument.REJETE]),
        ).order_by(Document.date_upload.desc()).limit(10)
        if cercle_id is not None:
            requete_depots = requete_depots.where(Document.cercle_id == cercle_id)
        mes_depots = session.exec(requete_depots).all()
    documents_affiches = [*documents, *mes_depots]
    fiches_documents = {
        document.id: _charger_fiche_pedagogique(document)
        for document in documents_affiches
    }
    fiches_documents_mg = {
        document.id: _charger_fiche_pedagogique_json(document.fiche_pedagogique_mg_json)
        for document in documents_affiches
    }

    # État du carnet de révision basé sur le document source, distinct
    # de la fiche pédagogique et du carnet individuel des classes virtuelles.
    ids_documents_affiches = [
        document.id for document in documents_affiches if document.id is not None
    ]
    fiches_revision_documents = {}
    if ids_documents_affiches:
        fiches_revision_documents = {
            fiche.document_id: fiche
            for fiche in session.exec(
                select(FicheRevisionDocument).where(
                    FicheRevisionDocument.document_id.in_(ids_documents_affiches)
                )
            ).all()
        }

    # Les cours historiques approuvés sans fiche sont préparés automatiquement
    # lors de la consultation de la bibliothèque. Le lot est borné pour ne pas
    # créer des centaines de tâches IA en une seule requête (la file est durable).
    if utilisateur:
        cours_sans_fiche = [
            int(document.id)
            for document in documents
            if document.type_document == TypeDocument.COURS
            and document.id is not None
            and document.id not in fiches_revision_documents
        ]
        for document_id in cours_sans_fiche[:10]:
            ai_queue.planifier_fiche_revision_document(document_id)

        # Répare en petit lot les fiches existantes dont la tâche durable a
        # disparu ou est terminée/échouée alors que la fiche prétend attendre.
        # Les tâches saines (en attente/en cours) ne sont pas renotifiées.
        cours_a_reparer = [
            int(document.id)
            for document in documents
            if document.type_document == TypeDocument.COURS
            and document.id is not None
            and (
                fiche := fiches_revision_documents.get(document.id)
            ) is not None
            and (
                fiche.statut in {
                    StatutFicheRevisionDocument.EN_ATTENTE,
                    StatutFicheRevisionDocument.EN_COURS,
                }
                or (
                    fiche.statut == StatutFicheRevisionDocument.TERMINEE
                    and str(fiche.contenu_json or "").strip() in {"", "{}"}
                )
            )
        ][:5]
        reparations = ai_queue.reparer_fiches_revision_documents_bloquees(
            max_documents=5,
            document_ids=cours_a_reparer,
        ) if cours_a_reparer else 0

        if cours_sans_fiche or reparations:
            fiches_revision_documents = {
                fiche.document_id: fiche
                for fiche in session.exec(
                    select(FicheRevisionDocument).where(
                        FicheRevisionDocument.document_id.in_(ids_documents_affiches)
                    )
                ).all()
            }

    return templates.TemplateResponse(
        "documents_list.html",
        {
            "request": request,
            "documents": documents,
            "mes_depots": mes_depots,
            "fiches_documents": fiches_documents,
            "fiches_documents_mg": fiches_documents_mg,
            "fiches_revision_documents": fiches_revision_documents,
            "filieres": filieres,
            "niveaux_scolaires": niveaux_scolaires,
            "options_scolaires": options_scolaires,
            "etablissements_scolaires": etablissements_scolaires,
            "filiere_id": filiere_id,
            "portee_academique": portee_academique or "",
            "niveau_scolaire_id": niveau_scolaire_id,
            "option_scolaire_id": option_scolaire_id,
            "etablissement_scolaire_id": etablissement_scolaire_id,
            "matiere": matiere or "",
            "type_document": type_document.value if type_document else "",
            "types_document": list(TypeDocument),
            "cercle": cercle,
            "utilisateur": utilisateur_courant(request, session),
        },
    )


@router.get("/cercles/{cercle_id}/documents")
def documents_du_cercle(cercle_id: int):
    """Alias lisible de /documents?cercle_id=... (lien affiche dans
    l'entete du salon de cercle, voir cercle_chat.html)."""
    return RedirectResponse(f"/documents?cercle_id={cercle_id}", status_code=307)


@router.get("/documents/upload")
def formulaire_upload(request: Request, cercle_id: Optional[int] = None, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    cercle = None
    if cercle_id is not None:
        if not _est_membre_cercle(session, cercle_id, utilisateur.id):
            return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)
        cercle = session.get(CercleEtude, cercle_id)
    filieres = session.exec(select(Filiere)).all()
    niveau_cercle_scolaire = (
        session.get(NiveauScolaire, cercle.niveau_scolaire_id)
        if cercle and cercle.niveau_scolaire_id else None
    )
    return templates.TemplateResponse(
        "document_upload.html",
        {
            "request": request,
            "filieres": filieres,
            "cercle": cercle,
            "niveau_cercle_scolaire": niveau_cercle_scolaire,
            "utilisateur": utilisateur,
        },
    )


@router.post("/documents/detect")
async def detect_document_automatique(
    request: Request,
    fichier: UploadFile = File(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Analyse le fichier sans le publier ni le conserver."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return JSONResponse({"ok": False, "erreur": "Connexion requise."}, status_code=401)

    host = request.client.host if request.client else "inconnu"
    if limite_depassee(f"detect-document:user:{utilisateur.id}", 30, 3600) or limite_depassee(
        f"detect-document:ip:{host}", 60, 3600
    ):
        return JSONResponse({"ok": False, "erreur": "Trop de détections. Réessayez plus tard."}, status_code=429)

    nom_fichier = fichier.filename or "document"
    suffixe = Path(nom_fichier).suffix.lower()
    extensions = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".jpg", ".jpeg", ".png"}
    if suffixe not in extensions:
        return JSONResponse({"ok": False, "erreur": "Format de fichier non pris en charge."}, status_code=400)

    contenu = await fichier.read()
    if not contenu:
        return JSONResponse({"ok": False, "erreur": "Le fichier est vide."}, status_code=400)
    if len(contenu) > 20 * 1024 * 1024:
        return JSONResponse({"ok": False, "erreur": "Le fichier dépasse 20 Mo."}, status_code=413)

    filieres = session.exec(select(Filiere)).all()
    if not filieres:
        return JSONResponse({"ok": False, "erreur": "Aucune filière disponible pour la détection."}, status_code=503)

    chemin_temp = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffixe) as tmp:
            tmp.write(contenu)
            chemin_temp = Path(tmp.name)

        texte = extraire_texte(str(chemin_temp))
        classification = classifier_document(
            nom_fichier=nom_fichier,
            texte=texte,
            filieres=filieres,
        )

        filiere_nom = ""
        if classification.filiere_id is not None:
            filiere = session.get(Filiere, classification.filiere_id)
            filiere_nom = filiere.nom if filiere else ""

        return JSONResponse({
            "ok": True,
            "detection": {
                "titre": classification.titre or "",
                "matiere": classification.matiere or "",
                "type_document": classification.type_document.value if classification.type_document else "",
                "annee": classification.annee or "",
                "filiere_id": classification.filiere_id or "",
                "filiere_nom": filiere_nom,
                "confiance": round(float(classification.confiance or 0.0), 3),
                "source": classification.source,
            },
        })
    except Exception:
        return JSONResponse(
            {"ok": False, "erreur": "La détection automatique n'a pas pu analyser ce fichier."},
            status_code=422,
        )
    finally:
        if chemin_temp is not None:
            try:
                chemin_temp.unlink(missing_ok=True)
            except Exception:
                pass


@router.post("/documents/upload")
def upload_document(
    request: Request,
    titre: Optional[str] = Form(default=""),
    matiere: Optional[str] = Form(default=""),
    type_document: Optional[TypeDocument] = Form(default=None),
    annee: Optional[int] = Form(default=None),
    filiere_id: Optional[int] = Form(default=None),
    portee_academique: str = Form(default="universitaire"),
    cycle_scolaire: Optional[str] = Form(default=None),
    niveau_scolaire_id: Optional[int] = Form(default=None),
    option_scolaire_id: Optional[int] = Form(default=None),
    etablissement_scolaire_id: Optional[int] = Form(default=None),
    cercle_id: Optional[int] = Form(default=None),
    classification_auto: bool = Form(default=False),
    fichier: UploadFile = File(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    host = request.client.host if request.client else "inconnu"
    if limite_depassee(f"upload-document:user:{utilisateur.id}", 20, 3600) or limite_depassee(
        f"upload-document:ip:{host}", 40, 3600
    ):
        return RedirectResponse("/documents?erreur=trop_de_depots", status_code=303)

    portee = (portee_academique or "universitaire").strip().lower()
    if portee not in {"universitaire", "scolaire"}:
        return RedirectResponse("/documents?erreur=portee_invalide", status_code=303)

    cercle = None
    if cercle_id is not None:
        cercle = session.get(CercleEtude, cercle_id)
        if not cercle or not _est_membre_cercle(session, cercle_id, utilisateur.id):
            return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)
        if cercle.portee_academique in {"universitaire", "scolaire"} and cercle.portee_academique != portee:
            return RedirectResponse("/documents?erreur=portee_cercle_invalide", status_code=303)

    # La classification IA actuelle ne dispose que du référentiel universitaire.
    # On refuse explicitement le mode auto scolaire plutôt que de créer une
    # fausse filière ou une ressource mal classée.
    if portee == "scolaire" and classification_auto:
        return RedirectResponse("/documents?erreur=classification_scolaire_non_disponible", status_code=303)

    niveau_scolaire = None
    option_scolaire = None
    etablissement_scolaire = None
    referentiel_courant = None

    if portee == "scolaire":
        if filiere_id is not None:
            return RedirectResponse("/documents?erreur=cible_scolaire_incoherente", status_code=303)
        cycle_scolaire = (cycle_scolaire or "").strip().lower()
        if cycle_scolaire not in {"college", "lycee"} or niveau_scolaire_id is None:
            return RedirectResponse("/documents?erreur=classe_scolaire_requise", status_code=303)

        referentiels_scolaires = session.exec(
            select(ReferentielScolaire).order_by(
                ReferentielScolaire.date_creation.desc(),
                ReferentielScolaire.id.desc(),
            )
        ).all()
        referentiel_courant = referentiels_scolaires[0] if referentiels_scolaires else None
        niveau_scolaire = session.get(NiveauScolaire, niveau_scolaire_id)
        if (
            not referentiel_courant
            or not niveau_scolaire
            or niveau_scolaire.referentiel_id != referentiel_courant.id
            or not niveau_scolaire.est_actif
            or niveau_scolaire.statut_validation != "verifie"
            or niveau_scolaire.cycle != cycle_scolaire
        ):
            return RedirectResponse("/documents?erreur=classe_scolaire_invalide", status_code=303)

        if option_scolaire_id is not None:
            option_scolaire = session.get(OptionScolaire, option_scolaire_id)
            if (
                not option_scolaire
                or option_scolaire.referentiel_id != referentiel_courant.id
                or option_scolaire.niveau_id != niveau_scolaire.id
                or not option_scolaire.est_active
                or option_scolaire.statut_validation != "verifie"
            ):
                return RedirectResponse("/documents?erreur=option_scolaire_invalide", status_code=303)

        if etablissement_scolaire_id is not None:
            etablissement_scolaire = session.get(EtablissementScolaire, etablissement_scolaire_id)
            if (
                not etablissement_scolaire
                or not etablissement_scolaire.est_actif
                or not etablissement_scolaire.est_verifie
            ):
                return RedirectResponse("/documents?erreur=etablissement_scolaire_invalide", status_code=303)

        # Un document déposé depuis un cercle scolaire doit suivre son ciblage.
        if cercle:
            if cercle.niveau_scolaire_id and cercle.niveau_scolaire_id != niveau_scolaire.id:
                return RedirectResponse("/documents?erreur=classe_cercle_incompatible", status_code=303)
            if cercle.option_scolaire_id and (
                not option_scolaire or cercle.option_scolaire_id != option_scolaire.id
            ):
                return RedirectResponse("/documents?erreur=option_cercle_incompatible", status_code=303)
            if cercle.etablissement_scolaire_id:
                if etablissement_scolaire and etablissement_scolaire.id != cercle.etablissement_scolaire_id:
                    return RedirectResponse("/documents?erreur=etablissement_cercle_incompatible", status_code=303)
                etablissement_scolaire = session.get(EtablissementScolaire, cercle.etablissement_scolaire_id)
                if not etablissement_scolaire or not etablissement_scolaire.est_actif or not etablissement_scolaire.est_verifie:
                    return RedirectResponse("/documents?erreur=etablissement_cercle_invalide", status_code=303)
                etablissement_scolaire_id = etablissement_scolaire.id

        filiere_id = None
    else:
        if any(value is not None for value in (niveau_scolaire_id, option_scolaire_id, etablissement_scolaire_id)):
            return RedirectResponse("/documents?erreur=cible_universitaire_incoherente", status_code=303)
        cycle_scolaire = None

    # Les métadonnées restent obligatoires hors détection automatique.
    if not classification_auto:
        if not (titre or "").strip() or not (matiere or "").strip() or type_document is None or annee is None:
            return RedirectResponse("/documents?erreur=metadonnees_manquantes", status_code=303)
        if portee == "universitaire" and filiere_id is None:
            return RedirectResponse("/documents?erreur=filiere_invalide", status_code=303)
        if annee < 2000 or annee > 2100:
            return RedirectResponse("/documents?erreur=annee_invalide", status_code=303)

    filieres_disponibles = session.exec(select(Filiere)).all()
    if portee == "universitaire" and not filieres_disponibles:
        return RedirectResponse("/documents?erreur=filiere_invalide", status_code=303)
    if classification_auto and not filieres_disponibles:
        return RedirectResponse("/documents?erreur=filiere_invalide", status_code=303)

    filiere_depart = session.get(Filiere, filiere_id) if filiere_id is not None else None
    if portee == "universitaire":
        filiere_reference = filiere_depart or filieres_disponibles[0]
    else:
        filiere_reference = None
    annee_reference = annee or datetime.utcnow().year
    reference_stockage = generer_reference(filiere_reference, annee_reference, session)
    nom_fichier_original = fichier.filename or "document"

    try:
        chemin_stocke = sauvegarder_fichier(fichier, reference_stockage)
    except FichierInvalide as erreur:
        return templates.TemplateResponse(
            "document_upload.html",
            {
                "request": request,
                "filieres": filieres_disponibles,
                "cercle": cercle,
                "erreur": str(erreur),
                "utilisateur": utilisateur,
            },
        )

    if classification_auto:
        try:
            with ouvrir_fichier_local(chemin_stocke) as chemin_local:
                texte_document = extraire_texte(str(chemin_local))

            classification = classifier_document(
                nom_fichier=nom_fichier_original,
                texte=texte_document,
                filieres=filieres_disponibles,
                titre_fourni=titre or "",
                matiere_fourni=matiere or "",
                type_fourni=type_document,
                annee_fournie=annee,
                filiere_id_fournie=filiere_id,
            )
            titre = classification.titre or titre or ""
            matiere = classification.matiere or matiere or ""
            type_document = classification.type_document or type_document
            annee = classification.annee or annee
            filiere_id = classification.filiere_id or filiere_id
        except Exception:
            # Le dépôt peut continuer avec les métadonnées manuelles, sans exposer
            # le contenu du fichier dans les logs.
            pass

    filiere = session.get(Filiere, filiere_id) if filiere_id is not None else None
    if portee == "universitaire" and not filiere:
        supprimer_fichier(chemin_stocke)
        return RedirectResponse("/documents?erreur=filiere_invalide", status_code=303)
    if portee == "scolaire" and filiere_id is not None:
        supprimer_fichier(chemin_stocke)
        return RedirectResponse("/documents?erreur=cible_scolaire_incoherente", status_code=303)
    if annee is None or annee < 2000 or annee > 2100:
        supprimer_fichier(chemin_stocke)
        return RedirectResponse("/documents?erreur=annee_invalide", status_code=303)
    if not (titre or "").strip() or not (matiere or "").strip() or type_document is None:
        supprimer_fichier(chemin_stocke)
        return RedirectResponse("/documents?erreur=metadonnees_manquantes", status_code=303)

    reference = generer_reference(filiere, annee, session)
    document = Document(
        reference=reference,
        titre=titre.strip(),
        matiere=matiere.strip(),
        type_document=type_document,
        annee=annee,
        filiere_id=filiere.id if filiere else None,
        portee_academique=portee,
        niveau_scolaire_id=niveau_scolaire.id if niveau_scolaire else None,
        option_scolaire_id=option_scolaire.id if option_scolaire else None,
        etablissement_scolaire_id=etablissement_scolaire.id if etablissement_scolaire else None,
        cercle_id=cercle_id,
        uploader_id=utilisateur.id,
        chemin_fichier=chemin_stocke,
        statut=StatutDocument.EN_ATTENTE,
    )
    session.add(document)
    session.commit()

    # La fiche pédagogique est créée hors requête HTTP ; un échec IA ne doit
    # pas empêcher l'enregistrement ni la modération du document.
    try:
        ai_queue.planifier_resume_document(document.id)
    except Exception:
        pass

    _notifier_admins_nouveau_document(session, document, utilisateur)
    gamification.enregistrer_action(
        session,
        utilisateur.id,
        "document",
        source_type="document",
        source_key=str(document.id),
    )
    session.commit()

    suffixe = "&classe=auto" if classification_auto else ""
    if cercle_id:
        return RedirectResponse(f"/documents?cercle_id={cercle_id}&envoye=1{suffixe}", status_code=303)
    return RedirectResponse(f"/documents?envoye=1&portee_academique={portee}{suffixe}", status_code=303)


@router.post("/documents/upload-multiple")
def upload_documents_multiples(
    request: Request,
    fichiers: list[UploadFile] = File(...),
    titre: Optional[str] = Form(default=""),
    matiere: Optional[str] = Form(default=""),
    type_document: Optional[TypeDocument] = Form(default=None),
    annee: Optional[int] = Form(default=None),
    filiere_id: Optional[int] = Form(default=None),
    portee_academique: str = Form(default="universitaire"),
    cercle_id: Optional[int] = Form(default=None),
    classification_auto: bool = Form(default=False),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Dépose un lot universitaire. Les cibles scolaires restent mono-fichier tant que le classifieur scolaire n'est pas disponible."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    portee = (portee_academique or "universitaire").strip().lower()
    if portee not in {"universitaire", "scolaire"}:
        return RedirectResponse("/documents?erreur=portee_invalide", status_code=303)
    if portee == "scolaire":
        # Ne jamais laisser un envoi multiple scolaire tomber sur le moteur
        # de classification universitaire par omission de métadonnées.
        return RedirectResponse("/documents?erreur=depot_scolaire_mono_fichier", status_code=303)

    filieres_disponibles = session.exec(select(Filiere)).all()
    cercle = session.get(CercleEtude, cercle_id) if cercle_id is not None else None

    def afficher_erreur(message: str, status_code: int = 400, details=None):
        return templates.TemplateResponse(
            "document_upload.html",
            {
                "request": request,
                "filieres": filieres_disponibles,
                "cercle": cercle,
                "erreur": message,
                "message": "",
                "erreurs_batch": details or [],
                "utilisateur": utilisateur,
            },
            status_code=status_code,
        )

    if not fichiers:
        return afficher_erreur("Sélectionnez au moins un fichier.")
    if len(fichiers) > 5:
        return afficher_erreur("Un envoi est limité à 5 fichiers. Sélectionnez un lot plus petit.")
    if not classification_auto:
        return afficher_erreur("Activez la détection automatique pour classer chaque fichier séparément.")
    if limite_depassee(f"upload-document:user:{utilisateur.id}", 20, 3600) or limite_depassee(
        f"upload-document:ip:{request.client.host if request.client else 'inconnu'}", 40, 3600
    ):
        return afficher_erreur("Trop de dépôts. Réessayez plus tard.", status_code=429)

    if cercle_id is not None:
        if not cercle or not _est_membre_cercle(session, cercle_id, utilisateur.id):
            return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)

    if not filieres_disponibles:
        return afficher_erreur("Aucune filière n'est disponible pour classer les documents.", status_code=503)
    filiere_depart = session.get(Filiere, filiere_id) if filiere_id is not None else None
    filiere_reference = filiere_depart or filieres_disponibles[0]
    annee_reference = annee or datetime.utcnow().year

    nombre_envoyes = 0
    erreurs_batch = []
    for fichier in fichiers:
        nom_fichier = Path(fichier.filename or "document").name
        chemin_stocke = None
        try:
            reference_stockage = generer_reference(filiere_reference, annee_reference, session)
            chemin_stocke = sauvegarder_fichier(fichier, reference_stockage)

            try:
                with ouvrir_fichier_local(chemin_stocke) as chemin_local:
                    texte_document = extraire_texte(str(chemin_local))
            except Exception:
                # Le nom de fichier et les métadonnées fournies peuvent encore
                # suffire à classer le document si l'extraction est indisponible.
                texte_document = ""

            classification = classifier_document(
                nom_fichier=nom_fichier,
                texte=texte_document or "",
                filieres=filieres_disponibles,
                titre_fourni=(titre or "") if len(fichiers) == 1 else "",
                matiere_fourni=matiere or "",
                type_fourni=type_document,
                annee_fournie=annee,
                filiere_id_fournie=filiere_id,
            )

            titre_final = (classification.titre or ((titre or "") if len(fichiers) == 1 else "")).strip()
            matiere_finale = (classification.matiere or matiere or "").strip()
            type_final = classification.type_document or type_document
            annee_finale = classification.annee or annee
            filiere_finale = session.get(Filiere, classification.filiere_id or filiere_id) if (classification.filiere_id or filiere_id) else None

            manquants = []
            if not titre_final:
                manquants.append("titre")
            if not matiere_finale:
                manquants.append("matière")
            if type_final is None:
                manquants.append("type")
            if annee_finale is None or annee_finale < 2000 or annee_finale > 2100:
                manquants.append("année")
            if filiere_finale is None:
                manquants.append("filière")
            if manquants:
                supprimer_fichier(chemin_stocke)
                erreurs_batch.append(
                    f"{nom_fichier} : informations insuffisantes ({', '.join(manquants)}). "
                    "Renommez le fichier avec la matière ou renseignez des informations communes, puis réessayez."
                )
                continue

            document = Document(
                reference=generer_reference(filiere_finale, annee_finale, session),
                titre=titre_final[:180],
                matiere=matiere_finale[:120],
                type_document=type_final,
                annee=annee_finale,
                filiere_id=filiere_finale.id,
                cercle_id=cercle_id,
                uploader_id=utilisateur.id,
                chemin_fichier=chemin_stocke,
                statut=StatutDocument.EN_ATTENTE,
            )
            try:
                session.add(document)
                session.commit()
                session.refresh(document)
                # Chaque fichier du lot possède sa propre fiche pédagogique.
                try:
                    ai_queue.planifier_resume_document(document.id)
                except Exception:
                    pass
            except Exception:
                session.rollback()
                supprimer_fichier(chemin_stocke)
                erreurs_batch.append(f"{nom_fichier} : impossible d'enregistrer le document. Réessayez.")
                continue

            nombre_envoyes += 1
            try:
                _notifier_admins_nouveau_document(session, document, utilisateur)
                gamification.enregistrer_action(
                    session,
                    utilisateur.id,
                    "document",
                    source_type="document",
                    source_key=str(document.id),
                )
                session.commit()
            except Exception:
                # Le document est déjà enregistré et reste en attente de modération.
                session.rollback()
        except FichierInvalide as erreur:
            if chemin_stocke:
                supprimer_fichier(chemin_stocke)
            erreurs_batch.append(f"{nom_fichier} : {erreur}")
        except Exception:
            session.rollback()
            if chemin_stocke:
                supprimer_fichier(chemin_stocke)
            erreurs_batch.append(
                f"{nom_fichier} : traitement impossible. Vérifiez le fichier et ses métadonnées."
            )

    if nombre_envoyes:
        message = (
            f"{nombre_envoyes} document(s) envoyé(s) pour validation. "
            "Ils seront publiés uniquement après approbation par un modérateur."
        )
    else:
        message = "Aucun document n'a pu être envoyé. Consultez les détails ci-dessous."

    return templates.TemplateResponse(
        "document_upload.html",
        {
            "request": request,
            "filieres": filieres_disponibles,
            "cercle": cercle,
            "erreur": "",
            "message": message,
            "erreurs_batch": erreurs_batch,
            "utilisateur": utilisateur,
        },
    )


@router.get("/documents/{document_id}/telecharger")
def telecharger_document(request: Request, document_id: int, session: Session = Depends(get_session)):
    """Téléchargement réservé aux comptes connectés et aux ressources autorisées.

    La bibliothèque peut présenter les métadonnées d'un document approuvé aux
    visiteurs, mais le fichier lui-même n'est jamais téléchargeable anonymement.
    Les ressources rattachées à un cercle restent réservées à ses membres.
    """
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        # Protéger également l'accès direct à l'URL, pas uniquement le bouton UI.
        return RedirectResponse("/connexion", status_code=303)

    document = session.get(Document, document_id)

    if not document or document.statut != StatutDocument.APPROUVE:
        return RedirectResponse("/documents", status_code=303)

    if document.cercle_id is not None:
        if not utilisateur or not _est_membre_cercle(session, document.cercle_id, utilisateur.id):
            return RedirectResponse(f"/cercles/{document.cercle_id}", status_code=303)

    if limite_depassee(f"telechargement-document:user:{utilisateur.id}", 60, 300):
        return RedirectResponse("/documents?erreur=trop_de_telechargements", status_code=303)

    document.nb_telechargements += 1
    session.add(document)
    session.commit()

    if utilisateur:
        session.add(ConsultationDocument(utilisateur_id=utilisateur.id, document_id=document.id))
        session.commit()

    if stockage_distant_actif():
        return RedirectResponse(obtenir_url_telechargement(document.chemin_fichier))
    return FileResponse(document.chemin_fichier, filename=Path(document.chemin_fichier).name)


@router.get("/moderation/{document_id}/consulter")
def consulter_document_moderation(
    request: Request,
    document_id: int,
    session: Session = Depends(get_session),
):
    """Ouvre une page de consultation sécurisée pour un administrateur.

    Le document n'a pas besoin d'être approuvé : l'administrateur doit pouvoir
    lire un document EN_ATTENTE ou REJETE avant de décider de son statut.
    """
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return RedirectResponse("/", status_code=303)

    document = session.get(Document, document_id)
    if not document:
        return _rediriger_moderation("introuvable")

    type_mime = mimetypes.guess_type(document.chemin_fichier)[0] or ""
    apercu_integrable = type_mime in {"application/pdf", "image/jpeg", "image/png"}

    texte_apercu = ""
    erreur_apercu = ""
    try:
        with ouvrir_fichier_local(document.chemin_fichier) as chemin_local:
            if not apercu_integrable:
                texte_apercu = (extraire_texte(str(chemin_local)) or "")[:18000]
            elif type_mime == "application/pdf":
                texte_apercu = ""
    except Exception:
        erreur_apercu = "Le contenu textuel n'a pas pu être extrait, mais le fichier peut encore être ouvert."

    return templates.TemplateResponse(
        request,
        "moderation_document_preview.html",
        {
            "utilisateur": utilisateur,
            "document": document,
            "type_mime": type_mime,
            "apercu_integrable": apercu_integrable,
            "texte_apercu": texte_apercu,
            "erreur_apercu": erreur_apercu,
            "fiche_document": _charger_fiche_pedagogique(document),
            "fiche_document_mg": _charger_fiche_pedagogique_json(document.fiche_pedagogique_mg_json),
        },
    )


@router.get("/moderation/{document_id}/fichier")
def fichier_document_moderation(
    request: Request,
    document_id: int,
    session: Session = Depends(get_session),
):
    """Sert temporairement le fichier à un administrateur uniquement."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return RedirectResponse("/", status_code=303)

    document = session.get(Document, document_id)
    if not document:
        return _rediriger_moderation("introuvable")

    nom = Path(document.chemin_fichier).name
    mime = mimetypes.guess_type(nom)[0] or "application/octet-stream"

    try:
        with ouvrir_fichier_local(document.chemin_fichier) as chemin_local:
            contenu = Path(chemin_local).read_bytes()
    except Exception:
        return _rediriger_moderation("fichier_indisponible")

    return Response(
        content=contenu,
        media_type=mime,
        headers={"Content-Disposition": f'inline; filename="{nom}"'},
    )


@router.get("/documents/{document_id}/apprendre")
def parcours_document(request: Request, document_id: int, session: Session = Depends(get_session)):
    """Hub d'apprentissage d'un document approuvé.

    Il ne remplace aucun flux existant : il ajoute un point d'entrée qui
    relie lecture, quiz et Tuteur contextualisé autour de la même ressource.
    """
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    document = session.get(Document, document_id)
    if not document or document.statut != StatutDocument.APPROUVE:
        return RedirectResponse("/documents", status_code=303)

    if document.cercle_id is not None and (
        not utilisateur or not _est_membre_cercle(session, document.cercle_id, utilisateur.id)
    ):
        return RedirectResponse(f"/cercles/{document.cercle_id}", status_code=303)

    fiche_revision_document = None
    if document.type_document == TypeDocument.COURS:
        fiche_revision_document = session.exec(
            select(FicheRevisionDocument).where(
                FicheRevisionDocument.document_id == document.id
            )
        ).first()
        if (
            fiche_revision_document is None
            or (
                fiche_revision_document.statut == StatutFicheRevisionDocument.TERMINEE
                and str(fiche_revision_document.contenu_json or "").strip() in {"", "{}"}
            )
        ):
            # Les anciens cours et les enregistrements terminés sans contenu
            # sont planifiés ou réparés à leur première consultation.
            session.commit()
            ai_queue.planifier_fiche_revision_document(document.id)
            session.expire_all()
            fiche_revision_document = session.exec(
                select(FicheRevisionDocument).where(
                    FicheRevisionDocument.document_id == document.id
                )
            ).first()
        elif fiche_revision_document.statut in {
            StatutFicheRevisionDocument.EN_ATTENTE,
            StatutFicheRevisionDocument.EN_COURS,
        }:
            ai_queue.reparer_fiches_revision_documents_bloquees(
                max_documents=1,
                document_ids=[int(document.id)],
            )
            session.expire_all()
            fiche_revision_document = session.exec(
                select(FicheRevisionDocument).where(
                    FicheRevisionDocument.document_id == document.id
                )
            ).first()

    return templates.TemplateResponse(
        "document_parcours.html",
        {
            "request": request,
            "utilisateur": utilisateur,
            "document": document,
            "fiche_pedagogique": _charger_fiche_pedagogique(document),
            "fiche_revision_document": fiche_revision_document,
            "peut_relancer_revision": (
                utilisateur.role == RoleUtilisateur.ADMIN
                or document.uploader_id == utilisateur.id
            ),
            "fiche_validee": _fiche_pedagogique_est_validee(document),
            "fiche_validation_possible": _fiche_pedagogique_peut_etre_validee(document),
            "types_document": list(TypeDocument),
            "peut_valider_fiche": (
                utilisateur.role == RoleUtilisateur.ADMIN
                or document.uploader_id == utilisateur.id
            ),
        },
    )


@router.get("/documents/{document_id}/revision")
def consulter_fiche_revision_document(
    request: Request,
    document_id: int,
    session: Session = Depends(get_session),
):
    """Affiche le carnet IA fondé sur le texte source d'un cours approuvé."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    document = session.get(Document, document_id)
    if (
        not document
        or document.statut != StatutDocument.APPROUVE
        or document.type_document != TypeDocument.COURS
    ):
        return RedirectResponse("/documents", status_code=303)
    if document.cercle_id is not None and not _est_membre_cercle(
        session, document.cercle_id, utilisateur.id
    ):
        return RedirectResponse(f"/cercles/{document.cercle_id}", status_code=303)

    fiche = session.exec(
        select(FicheRevisionDocument).where(
            FicheRevisionDocument.document_id == document_id
        )
    ).first()
    if (
        fiche is None
        or (
            fiche.statut == StatutFicheRevisionDocument.TERMINEE
            and str(fiche.contenu_json or "").strip() in {"", "{}"}
        )
    ):
        session.commit()
        ai_queue.planifier_fiche_revision_document(document_id)
        session.expire_all()
        fiche = session.exec(
            select(FicheRevisionDocument).where(
                FicheRevisionDocument.document_id == document_id
            )
        ).first()
    elif (
        fiche.statut == StatutFicheRevisionDocument.TERMINEE
        and fiche.version_generation != course_revision.VERSION_GENERATION_DOCUMENT
    ):
        # Régénère les fiches existantes une par une, uniquement lors d'une consultation.
        ai_queue.planifier_fiche_revision_document(document_id)
        session.expire_all()
        fiche = session.exec(
            select(FicheRevisionDocument).where(
                FicheRevisionDocument.document_id == document_id
            )
        ).first()
    elif fiche.statut in {
        StatutFicheRevisionDocument.EN_ATTENTE,
        StatutFicheRevisionDocument.EN_COURS,
    }:
        ai_queue.reparer_fiches_revision_documents_bloquees(
            max_documents=1,
            document_ids=[document_id],
        )
        session.expire_all()
        fiche = session.exec(
            select(FicheRevisionDocument).where(
                FicheRevisionDocument.document_id == document_id
            )
        ).first()

    if fiche is None or fiche.statut in {
        StatutFicheRevisionDocument.EN_ATTENTE,
        StatutFicheRevisionDocument.EN_COURS,
    }:
        return RedirectResponse(
            f"/documents/{document_id}/apprendre?revision=en_cours#revision-automatique",
            status_code=303,
        )
    if fiche.statut != StatutFicheRevisionDocument.TERMINEE or not fiche.contenu_json:
        return RedirectResponse(
            f"/documents/{document_id}/apprendre?revision=indisponible#revision-automatique",
            status_code=303,
        )

    try:
        contenu = course_revision.normaliser_fiche_revision(
            json.loads(fiche.contenu_json)
        )
        sources = json.loads(fiche.sources_json or "{}")
        if not isinstance(sources, dict):
            sources = {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return RedirectResponse(
            f"/documents/{document_id}/apprendre?revision=indisponible#revision-automatique",
            status_code=303,
        )

    # La fiche conservée en base reste commune et immuable. Chaque affichage reçoit
    # une copie adaptée au compte courant, à ses notions fragiles et à ses quiz.
    contenu = course_revision.personnaliser_fiche_revision_document(
        session, document, utilisateur.id, contenu
    )

    return templates.TemplateResponse(
        request,
        "document_revision.html",
        {
            "utilisateur": utilisateur,
            "document": document,
            "fiche_revision_document": fiche,
            "fiche_contenu": contenu,
            "fiche_sources": sources,
        },
    )


@router.get("/documents/{document_id}/revision/telecharger/{format_fichier}")
def telecharger_fiche_revision_document(
    request: Request,
    document_id: int,
    format_fichier: str,
    session: Session = Depends(get_session),
):
    """Télécharge le carnet source dans un format lisible, après recontrôle d'accès."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    if format_fichier not in {"pdf", "docx"}:
        return RedirectResponse("/documents", status_code=303)

    document = session.get(Document, document_id)
    if (
        not document
        or document.statut != StatutDocument.APPROUVE
        or document.type_document != TypeDocument.COURS
    ):
        return RedirectResponse("/documents", status_code=303)
    if document.cercle_id is not None and not _est_membre_cercle(
        session, document.cercle_id, utilisateur.id
    ):
        return RedirectResponse(f"/cercles/{document.cercle_id}", status_code=303)

    fiche = session.exec(
        select(FicheRevisionDocument).where(
            FicheRevisionDocument.document_id == document_id
        )
    ).first()
    if fiche and (
        fiche.statut == StatutFicheRevisionDocument.TERMINEE
        and fiche.version_generation != course_revision.VERSION_GENERATION_DOCUMENT
    ):
        ai_queue.planifier_fiche_revision_document(document_id)
        return RedirectResponse(
            f"/documents/{document_id}/apprendre?revision=en_cours#revision-automatique",
            status_code=303,
        )
    if not fiche or fiche.statut != StatutFicheRevisionDocument.TERMINEE or not fiche.contenu_json:
        return RedirectResponse(
            f"/documents/{document_id}/apprendre?revision=en_cours#revision-automatique",
            status_code=303,
        )

    try:
        contenu = course_revision.normaliser_fiche_revision(json.loads(fiche.contenu_json))
    except (TypeError, ValueError, json.JSONDecodeError):
        return RedirectResponse(
            f"/documents/{document_id}/apprendre?revision=indisponible#revision-automatique",
            status_code=303,
        )

    # Les exports PDF et Word reçoivent la même version privée que le navigateur.
    contenu = course_revision.personnaliser_fiche_revision_document(
        session, document, utilisateur.id, contenu
    )

    filiere = session.get(Filiere, document.filiere_id)
    cours_export = SimpleNamespace(
        nom=document.titre,
        matiere=document.matiere,
        niveau=(filiere.niveau if filiere else "Niveau non précisé"),
    )
    date_reference = fiche.date_generation or fiche.date_creation
    seance_export = SimpleNamespace(
        titre=f"Fiche de révision du document {document.reference}",
        date_fin_reelle=date_reference,
        date_creation=fiche.date_creation,
    )
    if format_fichier == "pdf":
        octets = course_revision.generer_pdf(
            contenu, cours_export, seance_export, utilisateur.nom
        )
        media_type = "application/pdf"
        extension = "pdf"
    else:
        octets = course_revision.generer_docx(
            contenu, cours_export, seance_export, utilisateur.nom
        )
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        extension = "docx"

    nom_fichier = f"mitaridala-revision-{document.id}-{document.reference}.{extension}"
    return Response(
        content=octets,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{nom_fichier}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/documents/{document_id}/revision/relancer")
def relancer_fiche_revision_document(
    request: Request,
    document_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Autorise l'auteur ou un administrateur à relancer une fiche qui a échoué."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    document = session.get(Document, document_id)
    if (
        not document
        or document.statut != StatutDocument.APPROUVE
        or document.type_document != TypeDocument.COURS
        or (
            utilisateur.role != RoleUtilisateur.ADMIN
            and document.uploader_id != utilisateur.id
        )
    ):
        return RedirectResponse("/documents", status_code=303)
    if document.cercle_id is not None and not _est_membre_cercle(
        session, document.cercle_id, utilisateur.id
    ) and utilisateur.role != RoleUtilisateur.ADMIN:
        return RedirectResponse(f"/cercles/{document.cercle_id}", status_code=303)

    fiche = session.exec(
        select(FicheRevisionDocument).where(
            FicheRevisionDocument.document_id == document_id
        )
    ).first()
    if not fiche or fiche.statut != StatutFicheRevisionDocument.ECHOUEE:
        return RedirectResponse(f"/documents/{document_id}/apprendre#revision-automatique", status_code=303)

    ai_queue.planifier_fiche_revision_document(document_id, forcer=True)
    return RedirectResponse(
        f"/documents/{document_id}/apprendre?revision=relancee#revision-automatique",
        status_code=303,
    )


@router.post("/documents/{document_id}/fiche/valider")
def valider_fiche_document(
    request: Request,
    document_id: int,
    resume_verifie: str = Form(...),
    matiere_verifiee: str = Form(default=""),
    type_document_verifie: Optional[TypeDocument] = Form(default=None),
    type_cours_verifie: str = Form(default=""),
    objectif_verifie: str = Form(default=""),
    niveau_verifie: str = Form(default=""),
    notions_verifiees: str = Form(default=""),
    confirmer_contenu: bool = Form(default=False),
    confirmer_metadonnees: bool = Form(default=False),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Enregistre la vérification humaine de la fiche et les corrections éventuelles."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    document = session.get(Document, document_id)
    if not document or document.statut != StatutDocument.APPROUVE:
        return RedirectResponse("/documents", status_code=303)
    if utilisateur.role != RoleUtilisateur.ADMIN and document.uploader_id != utilisateur.id:
        return RedirectResponse("/documents", status_code=303)
    if (
        document.cercle_id is not None
        and utilisateur.role != RoleUtilisateur.ADMIN
        and not _est_membre_cercle(session, document.cercle_id, utilisateur.id)
    ):
        return RedirectResponse(f"/cercles/{document.cercle_id}", status_code=303)
    if not _fiche_pedagogique_peut_etre_validee(document):
        return RedirectResponse(
            f"/documents/{document.id}/apprendre?erreur=fiche_indisponible#fiche-verification",
            status_code=303,
        )
    if not confirmer_contenu or not confirmer_metadonnees:
        return RedirectResponse(
            f"/documents/{document.id}/apprendre?erreur=confirmation_requise#fiche-verification",
            status_code=303,
        )

    matiere = " ".join(str(matiere_verifiee or "").split()).strip()[:120]
    if not matiere or not isinstance(type_document_verifie, TypeDocument):
        return RedirectResponse(
            f"/documents/{document.id}/apprendre?erreur=metadonnees_incompletes#fiche-verification",
            status_code=303,
        )

    resume = str(resume_verifie or "").strip()[:12000]
    type_cours = " ".join(str(type_cours_verifie or "").split()).strip()[:140]
    objectif = str(objectif_verifie or "").strip()[:800]
    niveau = str(niveau_verifie or "").strip()[:140]
    notions = []
    for ligne in (notions_verifiees or "").splitlines():
        valeur = " ".join(ligne.split()).strip()
        if valeur and valeur not in notions:
            notions.append(valeur[:180])
        if len(notions) >= 12:
            break
    if not resume:
        return RedirectResponse(
            f"/documents/{document.id}/apprendre?erreur=fiche_incomplete#fiche-verification",
            status_code=303,
        )

    fiche = _charger_fiche_pedagogique(document)
    ancienne_matiere = str(document.matiere or "")
    ancien_type_document = (
        document.type_document.value
        if isinstance(document.type_document, TypeDocument)
        else str(document.type_document or "")
    )
    nouveau_type_document = type_document_verifie.value
    anciens = {
        "resume": str(document.resume_ia or "").strip(),
        "type_cours": str(fiche.get("type_cours") or "").strip(),
        "objectif_pedagogique": str(fiche.get("objectif_pedagogique") or "").strip(),
        "niveau_cible": str(fiche.get("niveau_cible") or "").strip(),
        "notions_cles": [str(n).strip() for n in (fiche.get("notions_cles") or [])],
    }
    nouveau = {
        "resume": resume,
        "type_cours": type_cours,
        "objectif_pedagogique": objectif,
        "niveau_cible": niveau,
        "notions_cles": notions,
    }
    fiche_modifiee = anciens != nouveau
    metadata_modifiee = ancienne_matiere != matiere or ancien_type_document != nouveau_type_document
    date_validation = datetime.utcnow()

    fiche["resume"] = resume
    fiche["type_cours"] = type_cours
    fiche["objectif_pedagogique"] = objectif
    fiche["niveau_cible"] = niveau
    fiche["notions_cles"] = notions
    fiche["validation_humaine"] = True
    fiche["source_validation"] = "humaine"
    fiche["statut"] = "generee"
    fiche["validation_audit"] = {
        "valide_par_id": utilisateur.id,
        "valide_le": date_validation.isoformat(),
        "matiere_avant": ancienne_matiere,
        "matiere_apres": matiere,
        "type_document_avant": ancien_type_document,
        "type_document_apres": nouveau_type_document,
    }
    document.matiere = matiere
    document.type_document = type_document_verifie
    document.resume_ia = resume
    document.fiche_pedagogique_json = json.dumps(fiche, ensure_ascii=False)
    document.resume_statut_ia = "generee"
    document.fiche_validation_statut = "validee"
    document.fiche_validee_par_id = utilisateur.id
    document.fiche_validee_le = date_validation
    if fiche_modifiee or metadata_modifiee:
        document.resume_ia_mg = ""
        document.fiche_pedagogique_mg_json = "{}"
        document.resume_statut_ia_mg = "indisponible"

    session.add(document)
    session.commit()
    return RedirectResponse(
        f"/documents/{document.id}/apprendre?fiche=validee#fiche-verification",
        status_code=303,
    )


@router.get("/documents/{document_id}/quiz")
def quiz_document(request: Request, document_id: int, session: Session = Depends(get_session)):
    """Quiz genere par une vraie IA (API Groq, gratuite) a partir du texte
    extrait du document. Fonctionnalite Premium : necessite un essai
    gratuit actif ou un abonnement etudiant valide."""
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_premium_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    document = session.get(Document, document_id)
    if not document or document.statut != StatutDocument.APPROUVE:
        return RedirectResponse("/documents", status_code=303)
    if document.cercle_id is not None and (
        not utilisateur or not _est_membre_cercle(session, document.cercle_id, utilisateur.id)
    ):
        return RedirectResponse(f"/cercles/{document.cercle_id}", status_code=303)
    if not _fiche_pedagogique_est_validee(document):
        return RedirectResponse(
            f"/documents/{document.id}/apprendre?erreur=fiche_a_verifier#fiche-verification",
            status_code=303,
        )

    try:
        with ouvrir_fichier_local(document.chemin_fichier) as chemin_local:
            texte = extraire_texte(str(chemin_local))

        matiere_quiz = (document.matiere or document.titre or "Document").strip()[:120]
        questions_a_eviter = quiz_module._questions_vues_recemment(
            session, utilisateur.id, matiere_quiz
        )
        questions_a_eviter_essai = list(questions_a_eviter)
        empreintes_deja_vues = {
            empreinte
            for enonce in questions_a_eviter
            if (empreinte := quiz_module._empreinte_question({"question": enonce}))
        }
        structures_deja_vues = {
            structure
            for enonce in questions_a_eviter
            if (structure := quiz_module._structure_question({"question": enonce}))
        }
        questions_verifiees = None
        derniere_erreur = None
        for _essai in range(2):
            try:
                questions_generees = generer_quiz_depuis_texte(
                    texte,
                    nb_questions=5,
                    questions_a_eviter=questions_a_eviter_essai,
                )
                questions_courantes = valider_questions(
                    questions_generees, expected_count=5
                )
                empreintes = [
                    quiz_module._empreinte_question(question)
                    for question in questions_courantes
                ]
                structures = [
                    quiz_module._structure_question(question)
                    for question in questions_courantes
                ]
                if len(set(empreintes)) != len(empreintes):
                    questions_a_eviter_essai.extend(
                        question["question"] for question in questions_courantes
                    )
                    empreintes_deja_vues.update(empreintes)
                    structures_deja_vues.update(structures)
                    raise QuizValidationError("Le quiz du document contient des questions identiques.")
                if empreintes_deja_vues.intersection(empreintes):
                    questions_a_eviter_essai.extend(
                        question["question"] for question in questions_courantes
                    )
                    empreintes_deja_vues.update(empreintes)
                    structures_deja_vues.update(structures)
                    raise QuizValidationError("Le quiz du document répète une question récente.")
                if len(set(structures)) != len(structures):
                    questions_a_eviter_essai.extend(
                        question["question"] for question in questions_courantes
                    )
                    empreintes_deja_vues.update(empreintes)
                    structures_deja_vues.update(structures)
                    raise QuizValidationError(
                        "Le quiz du document contient plusieurs variantes numériques du même exercice."
                    )
                if structures_deja_vues.intersection(structures):
                    questions_a_eviter_essai.extend(
                        question["question"] for question in questions_courantes
                    )
                    empreintes_deja_vues.update(empreintes)
                    structures_deja_vues.update(structures)
                    raise QuizValidationError(
                        "Le quiz du document reprend un exercice récent en changeant seulement les nombres."
                    )
                questions_verifiees = questions_courantes
                break
            except QuizValidationError as erreur:
                derniere_erreur = erreur

        if questions_verifiees is None:
            raise QuizValidationError(
                "Impossible de générer un quiz documentaire suffisamment varié."
            ) from derniere_erreur
    except (QuizValidationError, ValueError):
        return RedirectResponse("/documents?erreur=generation_quiz", status_code=303)
    except Exception:
        return RedirectResponse("/documents?erreur=generation_quiz", status_code=303)

    niveau = getattr(utilisateur, "niveau", None) or "L1"
    tentative = TentativeQuiz(
        utilisateur_id=utilisateur.id,
        matiere=matiere_quiz,
        niveau=niveau,
        difficulte="Moyen",
        nb_questions=len(questions_verifiees),
        questions_json=json.dumps(questions_verifiees, ensure_ascii=False),
    )
    session.add(tentative)
    session.commit()
    session.refresh(tentative)

    try:
        ai_queue.planifier_verification_quiz(tentative.id)
    except Exception:
        pass

    return RedirectResponse(f"/quiz/{tentative.id}", status_code=303)


@router.get("/moderation")
def panneau_moderation(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return RedirectResponse("/", status_code=303)

    en_attente = session.exec(
        select(Document)
        .where(Document.statut == StatutDocument.EN_ATTENTE)
        .order_by(Document.date_upload.desc())
    ).all()
    approuves = session.exec(
        select(Document)
        .where(Document.statut == StatutDocument.APPROUVE)
        .order_by(Document.date_upload.desc())
    ).all()
    rejetes = session.exec(
        select(Document)
        .where(Document.statut == StatutDocument.REJETE)
        .order_by(Document.date_upload.desc())
    ).all()

    return templates.TemplateResponse(
        "moderation.html",
        {
            "request": request,
            "documents": en_attente,
            "documents_approuves": approuves,
            "documents_rejetes": rejetes,
            "utilisateur": utilisateur,
        },
    )


def _rediriger_moderation(resultat: str) -> RedirectResponse:
    return RedirectResponse(f"/moderation?resultat={resultat}", status_code=303)


def _normaliser_metadonnees_document(
    titre: str,
    matiere: str,
    type_document: str,
    annee: str,
    filiere_id: str,
) -> tuple[Optional[dict], Optional[str]]:
    """Valide et normalise les champs éditables par un administrateur."""
    titre_normalise = " ".join(str(titre or "").split()).strip()
    matiere_normalisee = " ".join(str(matiere or "").split()).strip()
    type_normalise = str(type_document or "").strip()
    annee_normalisee = str(annee or "").strip()
    filiere_normalisee = str(filiere_id or "").strip()

    if not titre_normalise:
        return None, "Le titre est obligatoire."
    if len(titre_normalise) > 240:
        return None, "Le titre ne peut pas dépasser 240 caractères."
    if not matiere_normalisee:
        return None, "La matière est obligatoire."
    if len(matiere_normalisee) > 120:
        return None, "La matière ne peut pas dépasser 120 caractères."

    try:
        type_valide = TypeDocument(type_normalise)
    except (TypeError, ValueError):
        return None, "Choisissez un type de document valide."

    try:
        annee_validee = int(annee_normalisee)
    except (TypeError, ValueError):
        return None, "L'année doit être un nombre entier."
    if not 1900 <= annee_validee <= 2100:
        return None, "L'année doit être comprise entre 1900 et 2100."

    try:
        filiere_validee = int(filiere_normalisee)
    except (TypeError, ValueError):
        return None, "Choisissez une filière valide."
    if filiere_validee < 1:
        return None, "Choisissez une filière valide."

    return {
        "titre": titre_normalise,
        "matiere": matiere_normalisee,
        "type_document": type_valide,
        "annee": annee_validee,
        "filiere_id": filiere_validee,
    }, None


@router.get("/moderation/{document_id}/modifier")
def formulaire_modifier_document(
    request: Request,
    document_id: int,
    session: Session = Depends(get_session),
):
    """Formulaire d'édition des métadonnées réservé aux administrateurs."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return RedirectResponse("/", status_code=303)

    document = session.get(Document, document_id)
    if not document:
        return _rediriger_moderation("introuvable")

    filieres = session.exec(select(Filiere).order_by(Filiere.nom)).all()
    champs_formulaire = ("titre", "matiere", "type_document", "annee", "filiere_id")
    valeurs = (
        {champ: request.query_params.get(champ, "") for champ in champs_formulaire}
        if any(champ in request.query_params for champ in champs_formulaire)
        else None
    )
    return templates.TemplateResponse(
        "moderation_document_modifier.html",
        {
            "request": request,
            "document": document,
            "filieres": filieres,
            "types_document": list(TypeDocument),
            "utilisateur": utilisateur,
            "erreur": request.query_params.get("erreur"),
            "resultat": request.query_params.get("resultat"),
            "valeurs": valeurs,
        },
    )


@router.post("/moderation/{document_id}/modifier")
def enregistrer_modification_document(
    request: Request,
    document_id: int,
    titre: str = Form(default=""),
    matiere: str = Form(default=""),
    type_document: str = Form(default=""),
    annee: str = Form(default=""),
    filiere_id: str = Form(default=""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Corrige les métadonnées sans modifier le fichier ni le statut de publication."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return RedirectResponse("/", status_code=303)

    document = session.get(Document, document_id)
    if not document:
        return _rediriger_moderation("introuvable")

    filieres = session.exec(select(Filiere).order_by(Filiere.nom)).all()
    valeurs = {
        "titre": titre or "",
        "matiere": matiere or "",
        "type_document": type_document or "",
        "annee": annee or "",
        "filiere_id": filiere_id or "",
    }

    def afficher_erreur(message: str) -> RedirectResponse:
        # Le JS de confirmation admin suit les redirections, mais présente
        # une alerte générique pour les réponses 4xx. Un 303 permet donc
        # d'afficher le message précis et de conserver les champs saisis.
        valeurs_limitees = {
            "titre": valeurs["titre"][:240],
            "matiere": valeurs["matiere"][:120],
            "type_document": valeurs["type_document"][:40],
            "annee": valeurs["annee"][:4],
            "filiere_id": valeurs["filiere_id"][:12],
        }
        query = urlencode({"erreur": message, **valeurs_limitees})
        return RedirectResponse(
            f"/moderation/{document.id}/modifier?{query}",
            status_code=303,
        )

    metadonnees, erreur = _normaliser_metadonnees_document(
        titre=titre,
        matiere=matiere,
        type_document=type_document,
        annee=annee,
        filiere_id=filiere_id,
    )
    if erreur:
        return afficher_erreur(erreur)

    filiere = session.get(Filiere, metadonnees["filiere_id"])
    if not filiere:
        return afficher_erreur("La filière sélectionnée n'existe plus. Choisissez-en une autre.")

    ancienne_filiere_id = document.filiere_id
    anciennes_matiere = document.matiere
    ancien_type = document.type_document
    changement_contexte_pedagogique = (
        anciennes_matiere != metadonnees["matiere"]
        or ancien_type != metadonnees["type_document"]
        or ancienne_filiere_id != metadonnees["filiere_id"]
    )
    modification = any((
        document.titre != metadonnees["titre"],
        anciennes_matiere != metadonnees["matiere"],
        ancien_type != metadonnees["type_document"],
        document.annee != metadonnees["annee"],
        ancienne_filiere_id != metadonnees["filiere_id"],
    ))
    if not modification:
        return _rediriger_moderation("inchange")

    document.titre = metadonnees["titre"]
    document.matiere = metadonnees["matiere"]
    document.type_document = metadonnees["type_document"]
    document.annee = metadonnees["annee"]
    document.filiere_id = metadonnees["filiere_id"]

    # Une fiche IA validée avec une ancienne matière, un ancien type ou une
    # autre filière ne doit plus être considérée comme validée sans contrôle.
    if changement_contexte_pedagogique:
        document.fiche_validation_statut = "a_verifier"
        document.fiche_validee_par_id = None
        document.fiche_validee_le = None
        document.resume_ia_mg = ""
        document.fiche_pedagogique_mg_json = "{}"
        document.resume_statut_ia_mg = "indisponible"

    fiche_revision_document = session.exec(
        select(FicheRevisionDocument).where(
            FicheRevisionDocument.document_id == document.id
        )
    ).first()
    if fiche_revision_document and modification:
        # Le titre/matière/niveau ont changé : ne servir pas un carnet lié à
        # d'anciennes métadonnées. Un recalcul sera mis en file après commit
        # si le document reste un cours approuvé.
        fiche_revision_document.statut = StatutFicheRevisionDocument.EN_ATTENTE
        fiche_revision_document.contenu_json = "{}"
        fiche_revision_document.sources_json = "{}"
        fiche_revision_document.erreur_generation = None
        fiche_revision_document.date_modification = datetime.utcnow()
        session.add(fiche_revision_document)

    est_cours_approuve = (
        document.statut == StatutDocument.APPROUVE
        and document.type_document == TypeDocument.COURS
    )
    session.add(document)
    session.commit()
    if est_cours_approuve:
        ai_queue.planifier_fiche_revision_document(document.id)
    return _rediriger_moderation(
        "metadonnees_modifiees" if changement_contexte_pedagogique else "modifie"
    )


@router.post("/moderation/{document_id}/approuver")
def approuver_document(
    request: Request,
    document_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return RedirectResponse("/", status_code=303)

    document = session.get(Document, document_id)
    if not document:
        return _rediriger_moderation("introuvable")

    document.statut = StatutDocument.APPROUVE
    session.add(document)
    _notifier_uploader_document(
        session,
        document,
        TypeNotification.DOCUMENT_APPROUVE,
        f"Ton document « {document.titre} » ({document.reference}) a été approuvé et est maintenant visible dans la bibliothèque.",
        acteur_id=utilisateur.id,
    )
    session.commit()
    if getattr(document, "type_document", None) == TypeDocument.COURS:
        # La génération du carnet est durable et asynchrone ; elle ne bloque
        # jamais la validation ni la mise à disposition du document source.
        ai_queue.planifier_fiche_revision_document(document.id)
    return _rediriger_moderation("approuve")


@router.post("/moderation/{document_id}/rejeter")
def rejeter_document(
    request: Request,
    document_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return RedirectResponse("/", status_code=303)

    document = session.get(Document, document_id)
    if not document:
        return _rediriger_moderation("introuvable")

    document.statut = StatutDocument.REJETE
    session.add(document)
    _notifier_uploader_document(
        session,
        document,
        TypeNotification.DOCUMENT_REJETE,
        f"Ton document « {document.titre} » ({document.reference}) a été rejeté et retiré de la bibliothèque publique.",
        acteur_id=utilisateur.id,
    )
    session.commit()
    return _rediriger_moderation("rejete")


@router.post("/moderation/{document_id}/supprimer")
def supprimer_document(
    request: Request,
    document_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Suppression définitive d'un document par un administrateur.

    Elle retire aussi les consultations et le fichier physique/objet distant
    avant de supprimer l'enregistrement Document.
    """
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return RedirectResponse("/", status_code=303)

    document = session.get(Document, document_id)
    if not document:
        return _rediriger_moderation("introuvable")

    for consultation in session.exec(
        select(ConsultationDocument).where(ConsultationDocument.document_id == document_id)
    ).all():
        session.delete(consultation)
    session.commit()

    _notifier_uploader_document(
        session,
        document,
        TypeNotification.DOCUMENT_SUPPRIME,
        f"Ton document « {document.titre} » ({document.reference}) a été supprimé définitivement par un administrateur.",
        acteur_id=utilisateur.id,
    )

    # Les tâches IA référencent le document : on les supprime d'abord pour
    # éviter une violation de clé étrangère lors de la suppression définitive.
    taches_document = session.exec(
        select(TacheIA).where(TacheIA.document_id == document_id)
    ).all()
    if taches_document:
        for tache in taches_document:
            session.delete(tache)
        session.commit()

    fiches_revision_document = session.exec(
        select(FicheRevisionDocument).where(
            FicheRevisionDocument.document_id == document_id
        )
    ).all()
    fiche_revision_document = fiches_revision_document[0] if fiches_revision_document else None
    if fiche_revision_document:
        taches_revision_document = session.exec(
            select(TacheIA).where(
                TacheIA.fiche_revision_document_id == fiche_revision_document.id
            )
        ).all()
        for tache in taches_revision_document:
            session.delete(tache)
        session.commit()
        session.delete(fiche_revision_document)
        session.commit()

    supprimer_fichier(document.chemin_fichier)

    session.delete(document)
    session.commit()

    return _rediriger_moderation("supprime")

