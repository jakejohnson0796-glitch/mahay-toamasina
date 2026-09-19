"""
Coeur de l'application : consulter, deposer, telecharger des documents,
et les valider (moderation) avant qu'ils soient publics.
"""
from pathlib import Path
from typing import Optional

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
    """Reference facon 'manifeste de cargo portuaire' : TOA-<FILIERE>-<ANNEE>-<NUMERO>.
    C'est le clin d'oeil a Toamasina (le port) qui sert de fil conducteur visuel."""
    prefixe = "".join(c for c in filiere.nom.upper() if c.isalpha())[:3]
    compteur = len(session.exec(select(Document)).all()) + 1
    return f"TOA-{prefixe}-{annee}-{compteur:04d}"


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
    titre: str = Form(...),
    matiere: str = Form(...),
    type_document: TypeDocument = Form(...),
    annee: int = Form(...),
    filiere_id: int = Form(...),
    cercle_id: Optional[int] = Form(default=None),
    fichier: UploadFile = File(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    # cercle_id vient d'un champ cache du formulaire (voir
    # document_upload.html) : on revalide quand meme l'appartenance
    # cote serveur, un utilisateur ne pouvant pas fabriquer une requete
    # avec un cercle_id arbitraire auquel il n'appartient pas.
    if cercle_id is not None and not _est_membre_cercle(session, cercle_id, utilisateur.id):
        cercle_id = None

    filiere = session.get(Filiere, filiere_id)
    reference = generer_reference(filiere, annee, session)
    # sauvegarder_fichier() choisit local ou Supabase Storage selon la
    # config (.env) — voir app/storage.py. Elle rejette aussi les types de
    # fichier non autorises et les fichiers trop volumineux (voir
    # FichierInvalide) : on rattrape l'erreur ici pour la montrer a
    # l'utilisateur plutot que de planter avec une 500.
    try:
        chemin_stocke = sauvegarder_fichier(fichier, reference)
    except FichierInvalide as erreur:
        filieres = session.exec(select(Filiere)).all()
        cercle = session.get(CercleEtude, cercle_id) if cercle_id else None
        return templates.TemplateResponse(
            "document_upload.html",
            {"request": request, "filieres": filieres, "cercle": cercle, "erreur": str(erreur)},
        )

    document = Document(
        reference=reference,
        titre=titre,
        matiere=matiere,
        type_document=type_document,
        annee=annee,
        filiere_id=filiere_id,
        cercle_id=cercle_id,
        uploader_id=utilisateur.id,
        chemin_fichier=chemin_stocke,
        statut=StatutDocument.EN_ATTENTE,  # visible seulement apres validation par un moderateur
    )
    session.add(document)
    session.commit()

    if cercle_id:
        return RedirectResponse(f"/documents?cercle_id={cercle_id}&envoye=1", status_code=303)
    return RedirectResponse("/documents?envoye=1", status_code=303)


@router.get("/documents/{document_id}/telecharger")
def telecharger_document(request: Request, document_id: int, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if not document or document.statut != StatutDocument.APPROUVE:
        return RedirectResponse("/documents", status_code=303)
    document.nb_telechargements += 1
    session.add(document)
    session.commit()

    utilisateur = utilisateur_courant(request, session)
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
    # Documents deja publics : l'admin doit aussi pouvoir en supprimer un
    # apres coup (contenu signale/problematique decouvert apres
    # approbation), pas seulement filtrer ceux encore en attente.
    approuves = session.exec(
        select(Document).where(Document.statut == StatutDocument.APPROUVE).order_by(Document.date_upload.desc())
    ).all()
    return templates.TemplateResponse(
        "moderation.html", {"request": request, "documents": en_attente, "documents_approuves": approuves}
    )


@router.post("/moderation/{document_id}/approuver")
def approuver_document(request: Request, document_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
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
def rejeter_document(request: Request, document_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return RedirectResponse("/", status_code=303)
    document = session.get(Document, document_id)
    if document:
        document.statut = StatutDocument.REJETE
        session.add(document)
        session.commit()
    return RedirectResponse("/moderation", status_code=303)


@router.post("/moderation/{document_id}/supprimer")
def supprimer_document(request: Request, document_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    """Suppression DEFINITIVE d'un document par un administrateur (retrait
    de contenu problematique/signale, pas un simple rejet de moderation).
    Reservee a l'admin — un utilisateur normal, meme uploader du document,
    ne peut jamais appeler cette route (verifie ici, pas seulement masque
    cote frontend).

    Nettoyage complet, dans cet ordre :
      1. lignes ConsultationDocument qui referencent ce document (evite
         une cle etrangere orpheline vers un Document supprime) ;
      2. fichier physique/objet distant (voir storage.supprimer_fichier) ;
      3. l'enregistrement Document lui-meme.
    Le fichier n'est jamais laisse orphelin sur le disque/bucket alors
    que son enregistrement en base a disparu, et inversement."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return RedirectResponse("/", status_code=303)

    document = session.get(Document, document_id)
    if not document:
        return RedirectResponse("/moderation", status_code=303)

    for consultation in session.exec(
        select(ConsultationDocument).where(ConsultationDocument.document_id == document_id)
    ).all():
        session.delete(consultation)
    session.commit()

    supprimer_fichier(document.chemin_fichier)

    session.delete(document)
    session.commit()

    return RedirectResponse("/moderation?supprime=1", status_code=303)
