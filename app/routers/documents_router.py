"""
Coeur de l'application : consulter, deposer, telecharger des documents,
et les valider (moderation) avant qu'ils soient publics.
"""
from pathlib import Path
from datetime import datetime
from typing import Optional
import secrets

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..models import Document, Filiere, TypeDocument, StatutDocument, RoleUtilisateur, ConsultationDocument, CercleEtude, MembreCercle
from ..auth import utilisateur_courant
from ..ai_quiz import generer_quiz_depuis_texte
from ..text_extraction import extraire_texte
from ..storage import sauvegarder_fichier, obtenir_url_telechargement, ouvrir_fichier_local, stockage_distant_actif, FichierInvalide, supprimer_fichier
from ..dependencies import acces_premium_ou_redirection
from ..web_utils import entier_ou_none
from .. import gamification
from ..rate_limit import limite_depassee
from ..document_classifier import classifier_document

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


def generer_reference(filiere: Filiere, annee: int, session: Session) -> str:
    """Reference unique sans charger/compter toute la table des documents."""
    prefixe = "".join(c for c in filiere.nom.upper() if c.isalpha())[:3] or "DOC"
    jeton = secrets.token_hex(4).upper()
    return f"MG-{prefixe}-{annee}-{jeton}"


@router.get("/documents")
def liste_documents(
    request: Request,
    filiere_id: Optional[str] = None,
    matiere: Optional[str] = None,
    type_document: Optional[TypeDocument] = None,
    cercle_id: Optional[int] = None,
    session: Session = Depends(get_session),
):
    filiere_id = entier_ou_none(filiere_id)
    cercle = None
    if cercle_id is not None:
        # Vue "Documents du cercle" : reservee aux membres, comme le salon
        # de discussion. Un document non-approuve reste invisible ici
        # aussi (meme garantie de moderation que la bibliotheque generale).
        utilisateur_pour_cercle = utilisateur_courant(request, session)
        if not utilisateur_pour_cercle or not _est_membre_cercle(session, cercle_id, utilisateur_pour_cercle.id):
            return RedirectResponse(f"/cercles/{cercle_id}", status_code=303)
        cercle = session.get(CercleEtude, cercle_id)
        if not cercle:
            return RedirectResponse("/cercles", status_code=303)

    requete = select(Document).where(Document.statut == StatutDocument.APPROUVE)
    if cercle_id is not None:
        requete = requete.where(Document.cercle_id == cercle_id)
    if filiere_id:
        requete = requete.where(Document.filiere_id == filiere_id)
    if matiere:
        requete = requete.where(Document.matiere.contains(matiere))
    if type_document:
        requete = requete.where(Document.type_document == type_document)
    documents = session.exec(requete.order_by(Document.date_upload.desc())).all()
    filieres = session.exec(select(Filiere)).all()

    return templates.TemplateResponse(
        "documents_list.html",
        {
            "request": request,
            "documents": documents,
            "filieres": filieres,
            "filiere_id": filiere_id,
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
    return templates.TemplateResponse(
        "document_upload.html",
        {"request": request, "filieres": filieres, "cercle": cercle, "utilisateur": utilisateur},
    )


@router.post("/documents/upload")
def upload_document(
    request: Request,
    titre: Optional[str] = Form(default=""),
    matiere: Optional[str] = Form(default=""),
    type_document: Optional[TypeDocument] = Form(default=None),
    annee: Optional[int] = Form(default=None),
    filiere_id: Optional[int] = Form(default=None),
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
    if limite_depassee(f"upload-document:user:{utilisateur.id}", 20, 3600) or limite_depassee(f"upload-document:ip:{host}", 40, 3600):
        return RedirectResponse("/documents?erreur=trop_de_depots", status_code=303)

    if cercle_id is not None and not _est_membre_cercle(session, cercle_id, utilisateur.id):
        cercle_id = None

    # Sans détection automatique, les métadonnées restent obligatoires.
    if not classification_auto:
        if not (titre or "").strip() or not (matiere or "").strip() or type_document is None or annee is None or filiere_id is None:
            return RedirectResponse("/documents?erreur=metadonnees_manquantes", status_code=303)
        if annee < 2000 or annee > 2100:
            return RedirectResponse("/documents?erreur=annee_invalide", status_code=303)

    # La référence utilisée pour le stockage peut être provisoire : en mode
    # automatique, la filière/année définitives ne sont connues qu'après
    # analyse du fichier.
    filiere_depart = session.get(Filiere, filiere_id) if filiere_id is not None else None
    filieres_disponibles = session.exec(select(Filiere)).all()
    if not filieres_disponibles:
        return RedirectResponse("/documents?erreur=filiere_invalide", status_code=303)

    filiere_reference = filiere_depart or filieres_disponibles[0]
    annee_reference = annee or datetime.utcnow().year
    reference_stockage = generer_reference(filiere_reference, annee_reference, session)
    nom_fichier_original = fichier.filename or "document"

    try:
        chemin_stocke = sauvegarder_fichier(fichier, reference_stockage)
    except FichierInvalide as erreur:
        cercle = session.get(CercleEtude, cercle_id) if cercle_id else None
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

    # Détection automatique : extraction locale puis IA facultative.
    # En cas d'échec, le dépôt ne doit jamais devenir une 500.
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
        except Exception as erreur:
            # On garde les valeurs saisies comme secours et on nettoie les
            # détails : le contenu du document ne doit pas apparaître dans
            # les logs de classification.
            pass

    filiere = session.get(Filiere, filiere_id) if filiere_id is not None else None
    if not filiere:
        supprimer_fichier(chemin_stocke)
        return RedirectResponse("/documents?erreur=filiere_invalide", status_code=303)
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
        filiere_id=filiere_id,
        cercle_id=cercle_id,
        uploader_id=utilisateur.id,
        chemin_fichier=chemin_stocke,
        statut=StatutDocument.EN_ATTENTE,
    )
    session.add(document)
    session.commit()

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
    return RedirectResponse(f"/documents?envoye=1{suffixe}", status_code=303)


@router.get("/documents/{document_id}/telecharger")
def telecharger_document(request: Request, document_id: int, session: Session = Depends(get_session)):
    """Telechargement d'un document approuve.

    Les documents generaux restent publics apres moderation. Un document
    rattache a un cercle, en revanche, reste prive aux membres de ce cercle
    (meme garde-fou que la liste /documents?cercle_id=...).
    """
    utilisateur = utilisateur_courant(request, session)
    document = session.get(Document, document_id)

    if not document or document.statut != StatutDocument.APPROUVE:
        return RedirectResponse("/documents", status_code=303)

    if document.cercle_id is not None:
        if not utilisateur or not _est_membre_cercle(session, document.cercle_id, utilisateur.id):
            return RedirectResponse(f"/cercles/{document.cercle_id}", status_code=303)

    host = request.client.host if request.client else "inconnu"
    if utilisateur:
        if limite_depassee(f"telechargement-document:user:{utilisateur.id}", 60, 300):
            return RedirectResponse("/documents?erreur=trop_de_telechargements", status_code=303)
    elif limite_depassee(f"telechargement-document:ip:{host}", 60, 300):
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

    with ouvrir_fichier_local(document.chemin_fichier) as chemin_local:
        texte = extraire_texte(str(chemin_local))

    quiz = generer_quiz_depuis_texte(texte)
    return templates.TemplateResponse(
        "quiz.html", {"request": request, "document": document, "quiz": quiz}
    )


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
    session.commit()
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

    supprimer_fichier(document.chemin_fichier)

    session.delete(document)
    session.commit()

    return _rediriger_moderation("supprime")

