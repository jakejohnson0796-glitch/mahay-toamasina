"""
Coeur de l'application : consulter, deposer, telecharger des documents,
et les valider (moderation) avant qu'ils soient publics.
"""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from ..database import get_session
from ..models import Document, Filiere, TypeDocument, StatutDocument, RoleUtilisateur
from ..auth import utilisateur_courant
from ..ai_quiz import generer_quiz_depuis_texte
from ..text_extraction import extraire_texte
from ..storage import sauvegarder_fichier, obtenir_url_telechargement, ouvrir_fichier_local, stockage_distant_actif
from ..dependencies import acces_premium_ou_redirection

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def generer_reference(filiere: Filiere, annee: int, session: Session) -> str:
    """Reference facon 'manifeste de cargo portuaire' : TOA-<FILIERE>-<ANNEE>-<NUMERO>.
    C'est le clin d'oeil a Toamasina (le port) qui sert de fil conducteur visuel."""
    prefixe = "".join(c for c in filiere.nom.upper() if c.isalpha())[:3]
    compteur = len(session.exec(select(Document)).all()) + 1
    return f"TOA-{prefixe}-{annee}-{compteur:04d}"


@router.get("/documents")
def liste_documents(
    request: Request,
    filiere_id: Optional[int] = None,
    matiere: Optional[str] = None,
    session: Session = Depends(get_session),
):
    filiere_id = int(filiere_id) if filiere_id else None
    requete = select(Document).where(Document.statut == StatutDocument.APPROUVE)
    if filiere_id:
        requete = requete.where(Document.filiere_id == filiere_id)
    if matiere:
        requete = requete.where(Document.matiere.contains(matiere))
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
            "utilisateur": utilisateur_courant(request, session),
        },
    )


@router.get("/documents/upload")
def formulaire_upload(request: Request, session: Session = Depends(get_session)):
    if not utilisateur_courant(request, session):
        return RedirectResponse("/connexion", status_code=303)
    filieres = session.exec(select(Filiere)).all()
    return templates.TemplateResponse("document_upload.html", {"request": request, "filieres": filieres})


@router.post("/documents/upload")
def upload_document(
    request: Request,
    titre: str = Form(...),
    matiere: str = Form(...),
    type_document: TypeDocument = Form(...),
    annee: int = Form(...),
    filiere_id: int = Form(...),
    fichier: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    filiere = session.get(Filiere, filiere_id)
    reference = generer_reference(filiere, annee, session)
    # sauvegarder_fichier() choisit local ou Supabase Storage selon la
    # config (.env) — voir app/storage.py.
    chemin_stocke = sauvegarder_fichier(fichier, reference)

    document = Document(
        reference=reference,
        titre=titre,
        matiere=matiere,
        type_document=type_document,
        annee=annee,
        filiere_id=filiere_id,
        uploader_id=utilisateur.id,
        chemin_fichier=chemin_stocke,
        statut=StatutDocument.EN_ATTENTE,  # visible seulement apres validation par un moderateur
    )
    session.add(document)
    session.commit()
    return RedirectResponse("/documents?envoye=1", status_code=303)


@router.get("/documents/{document_id}/telecharger")
def telecharger_document(document_id: int, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if not document or document.statut != StatutDocument.APPROUVE:
        return RedirectResponse("/documents", status_code=303)
    document.nb_telechargements += 1
    session.add(document)
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
    if not document:
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
    en_attente = session.exec(select(Document).where(Document.statut == StatutDocument.EN_ATTENTE)).all()
    return templates.TemplateResponse("moderation.html", {"request": request, "documents": en_attente})


@router.post("/moderation/{document_id}/approuver")
def approuver_document(request: Request, document_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return RedirectResponse("/", status_code=303)
    document = session.get(Document, document_id)
    if document:
        document.statut = StatutDocument.APPROUVE
        session.add(document)
        session.commit()
    return RedirectResponse("/moderation", status_code=303)


@router.post("/moderation/{document_id}/rejeter")
def rejeter_document(request: Request, document_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return RedirectResponse("/", status_code=303)
    document = session.get(Document, document_id)
    if document:
        document.statut = StatutDocument.REJETE
        session.add(document)
        session.commit()
    return RedirectResponse("/moderation", status_code=303)
