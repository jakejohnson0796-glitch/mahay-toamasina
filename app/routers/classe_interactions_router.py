"""Outils interactifs de séance : sondages, sous-salles, documents et transcription."""
import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlmodel import Session, select

from ..auth import utilisateur_courant
from ..config import parametres
from ..csrf import verifier_csrf
from ..database import get_session
from ..livekit_tokens import (
    LiveKitNonConfigure,
    arreter_agent_transcription,
    demarrer_agent_transcription,
    generer_jeton_salle,
    lister_participants_salle,
    livekit_configure,
)
from ..models import (
    AffectationSousSalle,
    ConsentementTranscription,
    Cours,
    Document,
    DocumentPartageSeance,
    GroupeSousSalle,
    InscriptionCours,
    ReponseSondageSeance,
    RoleUtilisateur,
    Seance,
    SondageSeance,
    StatutDocument,
    StatutSeance,
    TranscriptionSeance,
    Utilisateur,
)
from ..storage import obtenir_url_telechargement, stockage_distant_actif
from ..templating import templates
from .. import classe_transcription

router = APIRouter()


def _est_gerant(cours: Cours, utilisateur: Utilisateur) -> bool:
    return utilisateur.role == RoleUtilisateur.ADMIN or cours.professeur_id == utilisateur.id


def _est_inscrit(session: Session, cours_id: int, utilisateur_id: int) -> bool:
    return session.exec(
        select(InscriptionCours).where(
            InscriptionCours.cours_id == cours_id,
            InscriptionCours.utilisateur_id == utilisateur_id,
        )
    ).first() is not None


def _contexte_seance(request: Request, session: Session, seance_id: int):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return JSONResponse({"erreur": "Connexion requise."}, status_code=401)
    seance = session.get(Seance, seance_id)
    if not seance:
        return JSONResponse({"erreur": "Séance introuvable."}, status_code=404)
    cours = session.get(Cours, seance.cours_id)
    if not cours:
        return JSONResponse({"erreur": "Cours introuvable."}, status_code=404)
    gerant = _est_gerant(cours, utilisateur)
    if not gerant and not _est_inscrit(session, cours.id, utilisateur.id):
        return JSONResponse({"erreur": "Accès réservé aux membres de ce cours."}, status_code=403)
    if seance.statut != StatutSeance.EN_COURS:
        return JSONResponse({"erreur": "Cette séance n'est pas en cours."}, status_code=409)
    return utilisateur, seance, cours, gerant


def _options_sondage(sondage: SondageSeance) -> list[str]:
    try:
        options = json.loads(sondage.options_json)
    except (TypeError, ValueError):
        return []
    if not isinstance(options, list):
        return []
    return [str(item) for item in options if isinstance(item, str)]


def _resultats_sondage(session: Session, sondage: SondageSeance, utilisateur_id: int, gerant: bool) -> dict:
    options = _options_sondage(sondage)
    reponses = session.exec(
        select(ReponseSondageSeance).where(ReponseSondageSeance.sondage_id == sondage.id)
    ).all()
    compte = [0 for _ in options]
    for reponse in reponses:
        if 0 <= reponse.option_index < len(compte):
            compte[reponse.option_index] += 1
    ma_reponse = next((r.option_index for r in reponses if r.utilisateur_id == utilisateur_id), None)
    resultat_visible = gerant or not sondage.ouvert
    donnees = {
        "id": sondage.id,
        "question": sondage.question,
        "options": options,
        "type": sondage.type_sondage,
        "ouvert": sondage.ouvert,
        "a_repondu": ma_reponse is not None,
        "ma_reponse": ma_reponse,
        "nombre_reponses": len(reponses),
        "comptes": compte if resultat_visible else None,
        "bonne_option": sondage.bonne_option if resultat_visible and sondage.type_sondage == "quiz" else None,
        "date_creation": sondage.date_creation.isoformat(),
    }
    return donnees


@router.get("/classe/seances/{seance_id}/sondages")
def lister_sondages_seance(request: Request, seance_id: int, session: Session = Depends(get_session)):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    utilisateur, _seance, _cours, gerant = contexte
    sondages = session.exec(
        select(SondageSeance)
        .where(SondageSeance.seance_id == seance_id)
        .order_by(SondageSeance.date_creation.desc())
        .limit(20)
    ).all()
    return JSONResponse({
        "sondages": [
            _resultats_sondage(session, sondage, utilisateur.id, gerant)
            for sondage in sondages
        ]
    })


@router.post("/classe/seances/{seance_id}/sondages")
def creer_sondage_seance(
    request: Request,
    seance_id: int,
    question: str = Form(...),
    options: str = Form(...),
    type_sondage: str = Form("sondage"),
    bonne_option: Optional[int] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    utilisateur, seance, cours, gerant = contexte
    if not gerant:
        return JSONResponse({"erreur": "Seul le professeur peut lancer un sondage ou un quiz."}, status_code=403)
    question = (question or "").strip()
    choix = [ligne.strip() for ligne in (options or "").splitlines() if ligne.strip()]
    choix_uniques = {valeur.casefold() for valeur in choix}
    if not question or len(question) > 300:
        return JSONResponse({"erreur": "La question doit contenir de 1 à 300 caractères."}, status_code=422)
    if not 2 <= len(choix) <= 6 or len(choix_uniques) != len(choix) or any(len(x) > 120 for x in choix):
        return JSONResponse({"erreur": "Prévois 2 à 6 réponses différentes, de 120 caractères maximum."}, status_code=422)
    if type_sondage not in {"sondage", "quiz"}:
        return JSONResponse({"erreur": "Type d'interaction invalide."}, status_code=422)
    if type_sondage == "quiz" and (bonne_option is None or not 0 <= bonne_option < len(choix)):
        return JSONResponse({"erreur": "Choisis la bonne réponse du quiz."}, status_code=422)
    if type_sondage == "sondage":
        bonne_option = None
    # Une seule interaction reste ouverte à la fois dans une séance.
    anciennes = session.exec(
        select(SondageSeance).where(
            SondageSeance.seance_id == seance_id,
            SondageSeance.ouvert == True,  # noqa: E712
        )
    ).all()
    for ancienne in anciennes:
        ancienne.ouvert = False
        ancienne.date_cloture = datetime.utcnow()
        session.add(ancienne)
    sondage = SondageSeance(
        seance_id=seance.id,
        cours_id=cours.id,
        createur_id=utilisateur.id,
        question=question,
        options_json=json.dumps(choix, ensure_ascii=False),
        type_sondage=type_sondage,
        bonne_option=bonne_option,
        ouvert=True,
    )
    session.add(sondage)
    session.commit()
    session.refresh(sondage)
    return JSONResponse({"ok": True, "sondage": _resultats_sondage(session, sondage, utilisateur.id, True)})


@router.post("/classe/seances/{seance_id}/sondages/{sondage_id}/repondre")
def repondre_sondage_seance(
    request: Request,
    seance_id: int,
    sondage_id: int,
    option_index: int = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    utilisateur, _seance, _cours, gerant = contexte
    sondage = session.get(SondageSeance, sondage_id)
    if not sondage or sondage.seance_id != seance_id:
        return JSONResponse({"erreur": "Sondage introuvable."}, status_code=404)
    choix = _options_sondage(sondage)
    if not sondage.ouvert:
        return JSONResponse({"erreur": "Ce sondage est déjà clôturé."}, status_code=409)
    if not 0 <= option_index < len(choix):
        return JSONResponse({"erreur": "Réponse invalide."}, status_code=422)
    ancienne = session.exec(
        select(ReponseSondageSeance).where(
            ReponseSondageSeance.sondage_id == sondage.id,
            ReponseSondageSeance.utilisateur_id == utilisateur.id,
        )
    ).first()
    if ancienne:
        ancienne.option_index = option_index
        ancienne.date_creation = datetime.utcnow()
        session.add(ancienne)
    else:
        session.add(ReponseSondageSeance(
            sondage_id=sondage.id,
            utilisateur_id=utilisateur.id,
            option_index=option_index,
        ))
    session.commit()
    return JSONResponse({"ok": True, "sondage": _resultats_sondage(session, sondage, utilisateur.id, gerant)})


@router.post("/classe/seances/{seance_id}/sondages/{sondage_id}/cloturer")
def cloturer_sondage_seance(
    request: Request,
    seance_id: int,
    sondage_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    _utilisateur, _seance, _cours, gerant = contexte
    if not gerant:
        return JSONResponse({"erreur": "Action réservée au professeur."}, status_code=403)
    sondage = session.get(SondageSeance, sondage_id)
    if not sondage or sondage.seance_id != seance_id:
        return JSONResponse({"erreur": "Sondage introuvable."}, status_code=404)
    sondage.ouvert = False
    sondage.date_cloture = datetime.utcnow()
    session.add(sondage)
    session.commit()
    return JSONResponse({"ok": True})


@router.get("/classe/seances/{seance_id}/groupes")
def lister_groupes_sous_salles(request: Request, seance_id: int, session: Session = Depends(get_session)):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    utilisateur, _seance, _cours, gerant = contexte
    groupes = session.exec(
        select(GroupeSousSalle)
        .where(GroupeSousSalle.seance_id == seance_id)
        .order_by(GroupeSousSalle.id)
    ).all()
    resultats = []
    for groupe in groupes:
        affectations = session.exec(
            select(AffectationSousSalle).where(AffectationSousSalle.groupe_id == groupe.id)
        ).all()
        ids = [a.utilisateur_id for a in affectations]
        if not gerant and utilisateur.id not in ids:
            continue
        noms = []
        if gerant and ids:
            utilisateurs = session.exec(select(Utilisateur).where(Utilisateur.id.in_(ids))).all()
            noms = [u.nom for u in utilisateurs]
        resultats.append({
            "id": groupe.id,
            "nom": groupe.nom,
            "nombre_membres": len(ids),
            "membres": noms if gerant else [],
            "rejoindre_url": f"/classe/seances/{seance_id}/groupes/{groupe.id}/rejoindre",
            "est_mon_groupe": utilisateur.id in ids,
        })
    return JSONResponse({"groupes": resultats, "peut_gerer": gerant})


@router.post("/classe/seances/{seance_id}/groupes")
def creer_groupes_sous_salles(
    request: Request,
    seance_id: int,
    nombre_groupes: int = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    _utilisateur, seance, cours, gerant = contexte
    if not gerant:
        return JSONResponse({"erreur": "Seul le professeur peut créer les sous-salles."}, status_code=403)
    inscrits = session.exec(
        select(InscriptionCours)
        .where(InscriptionCours.cours_id == cours.id)
        .order_by(InscriptionCours.utilisateur_id)
    ).all()
    eleves = [inscription.utilisateur_id for inscription in inscrits]
    if len(eleves) < 2:
        return JSONResponse({"erreur": "Il faut au moins deux élèves inscrits pour ouvrir des sous-salles."}, status_code=409)
    if not 2 <= nombre_groupes <= min(12, len(eleves)):
        return JSONResponse({"erreur": f"Choisis de 2 à {min(12, len(eleves))} groupes."}, status_code=422)

    anciens_groupes = session.exec(
        select(GroupeSousSalle).where(GroupeSousSalle.seance_id == seance_id)
    ).all()
    for ancien in anciens_groupes:
        affectations = session.exec(
            select(AffectationSousSalle).where(AffectationSousSalle.groupe_id == ancien.id)
        ).all()
        for affectation in affectations:
            session.delete(affectation)
        session.delete(ancien)
    session.commit()

    groupes = []
    for index in range(nombre_groupes):
        groupe = GroupeSousSalle(
            seance_id=seance_id,
            nom=f"Groupe {index + 1}",
            nom_salle_livekit=f"{seance.nom_salle_livekit[:100]}-sous-{secrets.token_hex(10)}",
        )
        session.add(groupe)
        groupes.append(groupe)
    session.commit()
    for groupe in groupes:
        session.refresh(groupe)
    for index, utilisateur_id in enumerate(eleves):
        session.add(AffectationSousSalle(
            seance_id=seance_id,
            groupe_id=groupes[index % nombre_groupes].id,
            utilisateur_id=utilisateur_id,
        ))
    session.commit()
    return JSONResponse({"ok": True, "nombre_groupes": nombre_groupes, "nombre_eleves_affectes": len(eleves)})


@router.get("/classe/seances/{seance_id}/groupes/{groupe_id}/rejoindre")
def rejoindre_sous_salle(
    request: Request,
    seance_id: int,
    groupe_id: int,
    session: Session = Depends(get_session),
):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    utilisateur, _seance, _cours, gerant = contexte
    groupe = session.get(GroupeSousSalle, groupe_id)
    if not groupe or groupe.seance_id != seance_id:
        return JSONResponse({"erreur": "Sous-salle introuvable."}, status_code=404)
    affectation = session.exec(
        select(AffectationSousSalle).where(
            AffectationSousSalle.groupe_id == groupe.id,
            AffectationSousSalle.utilisateur_id == utilisateur.id,
        )
    ).first()
    if not gerant and not affectation:
        return JSONResponse({"erreur": "Tu n'es pas affecté à cette sous-salle."}, status_code=403)
    if not livekit_configure():
        return JSONResponse({"erreur": "Le service vidéo n'est pas configuré."}, status_code=503)
    try:
        token = generer_jeton_salle(
            nom_salle=groupe.nom_salle_livekit,
            utilisateur_id=utilisateur.id,
            nom_affiche=utilisateur.nom,
            peut_publier=True,
            peut_partager_ecran=gerant,
        )
    except LiveKitNonConfigure as erreur:
        return JSONResponse({"erreur": str(erreur)}, status_code=503)
    return templates.TemplateResponse(
        request,
        "classe_sous_salle.html",
        {
            "utilisateur": utilisateur,
            "groupe": groupe,
            "url_livekit": parametres.livekit_url,
            "jeton_livekit": token,
            "jeton_csrf": request.session.get("_csrf_token", ""),
            "peut_gerer": gerant,
        },
    )


@router.get("/classe/seances/{seance_id}/documents")
def lister_documents_seance(request: Request, seance_id: int, session: Session = Depends(get_session)):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    _utilisateur, _seance, cours, gerant = contexte
    partages = session.exec(
        select(DocumentPartageSeance).where(DocumentPartageSeance.seance_id == seance_id)
    ).all()
    ids_partages = [partage.document_id for partage in partages]
    documents_partages = []
    if ids_partages:
        documents_partages = session.exec(
            select(Document).where(
                Document.id.in_(ids_partages),
                Document.statut == StatutDocument.APPROUVE,
            ).order_by(Document.titre)
        ).all()
    disponibles = []
    if gerant:
        disponibles = session.exec(
            select(Document)
            .where(
                Document.statut == StatutDocument.APPROUVE,
                Document.matiere == cours.matiere,
            )
            .order_by(Document.date_upload.desc())
            .limit(40)
        ).all()
    return JSONResponse({
        "partages": [
            {"id": d.id, "titre": d.titre, "matiere": d.matiere,
             "ouvrir_url": f"/classe/seances/{seance_id}/documents/{d.id}/ouvrir"}
            for d in documents_partages
        ],
        "disponibles": [
            {"id": d.id, "titre": d.titre, "type": d.type_document.value if hasattr(d.type_document, "value") else str(d.type_document)}
            for d in disponibles if d.id not in ids_partages
        ],
        "peut_gerer": gerant,
    })


@router.post("/classe/seances/{seance_id}/documents/partager")
def partager_document_seance(
    request: Request,
    seance_id: int,
    document_id: int = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    utilisateur, _seance, cours, gerant = contexte
    if not gerant:
        return JSONResponse({"erreur": "Seul le professeur peut partager un document."}, status_code=403)
    document = session.get(Document, document_id)
    if (
        not document
        or document.statut != StatutDocument.APPROUVE
        or document.matiere.strip().casefold() != cours.matiere.strip().casefold()
    ):
        return JSONResponse({"erreur": "Ce document n'est pas approuvé ou ne correspond pas à la matière du cours."}, status_code=404)
    partage = session.exec(
        select(DocumentPartageSeance).where(
            DocumentPartageSeance.seance_id == seance_id,
            DocumentPartageSeance.document_id == document_id,
        )
    ).first()
    if not partage:
        session.add(DocumentPartageSeance(
            seance_id=seance_id,
            cours_id=cours.id,
            document_id=document_id,
            partage_par_id=utilisateur.id,
        ))
        session.commit()
    return JSONResponse({"ok": True})


@router.get("/classe/seances/{seance_id}/documents/{document_id}/ouvrir")
def ouvrir_document_partage(request: Request, seance_id: int, document_id: int, session: Session = Depends(get_session)):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    _utilisateur, _seance, _cours, _gerant = contexte
    partage = session.exec(
        select(DocumentPartageSeance).where(
            DocumentPartageSeance.seance_id == seance_id,
            DocumentPartageSeance.document_id == document_id,
        )
    ).first()
    document = session.get(Document, document_id)
    if not partage or not document or document.statut != StatutDocument.APPROUVE:
        return JSONResponse({"erreur": "Document non partagé ou indisponible."}, status_code=404)
    try:
        cible = obtenir_url_telechargement(document.chemin_fichier, telechargement=True)
    except Exception:
        return JSONResponse({"erreur": "Le document est temporairement indisponible."}, status_code=503)
    if stockage_distant_actif():
        return RedirectResponse(cible, status_code=303)
    chemin = Path(cible)
    if not chemin.is_file():
        return JSONResponse({"erreur": "Fichier introuvable dans le stockage local."}, status_code=404)
    return FileResponse(path=chemin, filename=chemin.name)


def _obtenir_consentement(session: Session, seance_id: int, utilisateur_id: int):
    return session.exec(
        select(ConsentementTranscription).where(
            ConsentementTranscription.seance_id == seance_id,
            ConsentementTranscription.utilisateur_id == utilisateur_id,
        )
    ).first()


def _enregistrer_consentement(session: Session, seance_id: int, utilisateur_id: int, consenti: bool):
    consentement = _obtenir_consentement(session, seance_id, utilisateur_id)
    maintenant = datetime.utcnow()
    if consentement:
        consentement.consenti = consenti
        consentement.date_modification = maintenant
        session.add(consentement)
    else:
        session.add(ConsentementTranscription(
            seance_id=seance_id,
            utilisateur_id=utilisateur_id,
            consenti=consenti,
            date_creation=maintenant,
            date_modification=maintenant,
        ))
    session.commit()


async def _arreter_transcription(session: Session, seance: Seance, transcription: TranscriptionSeance):
    if transcription.active and transcription.agent_dispatch_id:
        await arreter_agent_transcription(seance.nom_salle_livekit, transcription.agent_dispatch_id)
    transcription.active = False
    transcription.agent_dispatch_id = None
    transcription.date_fin = datetime.utcnow()
    transcription.date_modification = datetime.utcnow()
    session.add(transcription)
    session.commit()


@router.get("/classe/seances/{seance_id}/transcription")
def etat_transcription(request: Request, seance_id: int, session: Session = Depends(get_session)):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    utilisateur, _seance, _cours, gerant = contexte
    consentement = _obtenir_consentement(session, seance_id, utilisateur.id)
    transcription = session.exec(
        select(TranscriptionSeance).where(TranscriptionSeance.seance_id == seance_id)
    ).first()
    return JSONResponse({
        "consenti": bool(consentement and consentement.consenti),
        "active": bool(transcription and transcription.active),
        "agent_configure": bool(parametres.livekit_transcription_agent_name),
        "contenu": transcription.contenu if transcription and not transcription.active else "",
        "resume": transcription.resume_ia if transcription else "",
        "peut_gerer": gerant,
    })


@router.post("/classe/seances/{seance_id}/transcription/consentir")
async def consentir_transcription(
    request: Request,
    seance_id: int,
    consenti: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    utilisateur, seance, _cours, _gerant = contexte
    valeur = consenti.strip().lower() in {"1", "true", "oui", "on"}
    _enregistrer_consentement(session, seance_id, utilisateur.id, valeur)
    if not valeur:
        transcription = session.exec(
            select(TranscriptionSeance).where(TranscriptionSeance.seance_id == seance_id)
        ).first()
        if transcription and transcription.active:
            try:
                await _arreter_transcription(session, seance, transcription)
            except Exception:
                return JSONResponse({
                    "erreur": "Le retrait de consentement est enregistré, mais l'arrêt de l'agent n'a pas pu être confirmé. Préviens le professeur avant de poursuivre."
                }, status_code=503)
    return JSONResponse({"ok": True, "consenti": valeur})


@router.get("/classe/seances/{seance_id}/transcription/consentement")
def page_consentement_transcription(request: Request, seance_id: int, session: Session = Depends(get_session)):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    utilisateur, _seance, cours, _gerant = contexte
    return templates.TemplateResponse(
        request,
        "classe_transcription_consentement.html",
        {
            "utilisateur": utilisateur,
            "cours": cours,
            "seance_id": seance_id,
        },
    )


@router.post("/classe/seances/{seance_id}/transcription/consentement")
async def choisir_consentement_transcription(
    request: Request,
    seance_id: int,
    choix: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    utilisateur, seance, cours, _gerant = contexte
    if choix not in {"accepter", "refuser"}:
        return JSONResponse({"erreur": "Choix de consentement invalide."}, status_code=422)
    consent = choix == "accepter"
    _enregistrer_consentement(session, seance_id, utilisateur.id, consent)
    if not consent:
        transcription = session.exec(
            select(TranscriptionSeance).where(TranscriptionSeance.seance_id == seance_id)
        ).first()
        if transcription and transcription.active:
            try:
                await _arreter_transcription(session, seance, transcription)
            except Exception:
                return JSONResponse({"erreur": "L'arrêt de la transcription n'a pas pu être confirmé. Le professeur doit arrêter l'agent."}, status_code=503)
        return RedirectResponse(f"/classe/seances/{seance_id}/salle", status_code=303)
    return RedirectResponse(f"/classe/seances/{seance_id}/salle", status_code=303)


@router.post("/classe/seances/{seance_id}/transcription/demarrer")
async def demarrer_transcription_seance(
    request: Request,
    seance_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    utilisateur, seance, _cours, gerant = contexte
    if not gerant:
        return JSONResponse({"erreur": "Seul le professeur peut démarrer la transcription."}, status_code=403)
    nom_agent = parametres.livekit_transcription_agent_name
    if not nom_agent:
        return JSONResponse({"erreur": "La transcription n'est pas configurée : le worker LiveKit dédié doit être déployé et son nom défini côté serveur."}, status_code=503)
    if not livekit_configure():
        return JSONResponse({"erreur": "LiveKit n'est pas configuré."}, status_code=503)
    transcription = session.exec(
        select(TranscriptionSeance).where(TranscriptionSeance.seance_id == seance_id)
    ).first()
    if transcription and transcription.active:
        return JSONResponse({"erreur": "La transcription est déjà active."}, status_code=409)
    try:
        identites = await lister_participants_salle(seance.nom_salle_livekit)
    except Exception:
        return JSONResponse({"erreur": "Impossible de vérifier la liste des participants LiveKit."}, status_code=503)
    # Chaque participant doit être identifiable par un compte Mahay. On ne
    # démarre pas si une identité inconnue pourrait être transcrite sans accord.
    if any(not identite.isdigit() for identite in identites):
        return JSONResponse({"erreur": "Un participant ne peut pas être identifié par Mahay. La transcription reste désactivée tant que tous les participants ne sont pas identifiés."}, status_code=409)
    identites_utilisateurs = identites
    if not identites_utilisateurs or str(utilisateur.id) not in identites_utilisateurs:
        return JSONResponse({"erreur": "Le professeur doit être connecté à la salle pour démarrer la transcription."}, status_code=409)
    ids = [int(identite) for identite in identites_utilisateurs]
    consentements = session.exec(
        select(ConsentementTranscription).where(
            ConsentementTranscription.seance_id == seance_id,
            ConsentementTranscription.utilisateur_id.in_(ids),
            ConsentementTranscription.consenti == True,  # noqa: E712
        )
    ).all()
    accordes = {c.utilisateur_id for c in consentements}
    if any(uid not in accordes for uid in ids):
        return JSONResponse({
            "erreur": "Tous les participants actuellement connectés doivent donner leur accord avant le démarrage.",
            "nombre_participants": len(ids),
            "nombre_accords": len(accordes),
        }, status_code=409)
    try:
        dispatch_id = await demarrer_agent_transcription(
            seance.nom_salle_livekit,
            nom_agent,
            json.dumps({"seance_id": seance_id, "langue": "fr"}, ensure_ascii=False),
        )
    except Exception:
        return JSONResponse({"erreur": "Le worker de transcription n'est pas joignable. Vérifie son déploiement LiveKit."}, status_code=503)
    if not transcription:
        transcription = TranscriptionSeance(seance_id=seance_id, demarree_par_id=utilisateur.id)
    transcription.demarree_par_id = utilisateur.id
    transcription.agent_dispatch_id = dispatch_id
    transcription.active = True
    transcription.date_debut = datetime.utcnow()
    transcription.date_fin = None
    transcription.date_modification = datetime.utcnow()
    session.add(transcription)
    session.commit()
    return JSONResponse({"ok": True, "active": True})


@router.post("/classe/seances/{seance_id}/transcription/arreter")
async def arreter_transcription_seance(
    request: Request,
    seance_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    _utilisateur, seance, _cours, gerant = contexte
    if not gerant:
        return JSONResponse({"erreur": "Seul le professeur peut arrêter la transcription."}, status_code=403)
    transcription = session.exec(
        select(TranscriptionSeance).where(TranscriptionSeance.seance_id == seance_id)
    ).first()
    if not transcription or not transcription.active:
        return JSONResponse({"ok": True, "active": False})
    try:
        await _arreter_transcription(session, seance, transcription)
    except Exception:
        return JSONResponse({"erreur": "L'agent n'a pas confirmé son arrêt. Réessaie ou vérifie le worker."}, status_code=503)
    return JSONResponse({"ok": True, "active": False})


@router.post("/classe/seances/{seance_id}/transcription/enregistrer")
def enregistrer_transcription(
    request: Request,
    seance_id: int,
    contenu: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    utilisateur, _seance, _cours, gerant = contexte
    if not gerant:
        return JSONResponse({"erreur": "Seul le professeur peut enregistrer le compte rendu."}, status_code=403)
    texte = (contenu or "").strip()
    if not texte or len(texte) > 100000:
        return JSONResponse({"erreur": "Le compte rendu doit contenir de 1 à 100 000 caractères."}, status_code=422)
    transcription = session.exec(
        select(TranscriptionSeance).where(TranscriptionSeance.seance_id == seance_id)
    ).first()
    if not transcription or transcription.active:
        return JSONResponse({"erreur": "Arrête la transcription avant d'enregistrer le compte rendu."}, status_code=409)
    transcription.contenu = texte
    transcription.resume_ia = ""
    transcription.date_modification = datetime.utcnow()
    session.add(transcription)
    session.commit()
    return JSONResponse({"ok": True})


@router.post("/classe/seances/{seance_id}/transcription/resumer")
def resumer_transcription_seance(
    request: Request,
    seance_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    contexte = _contexte_seance(request, session, seance_id)
    if isinstance(contexte, JSONResponse):
        return contexte
    _utilisateur, _seance, cours, gerant = contexte
    if not gerant:
        return JSONResponse({"erreur": "Seul le professeur peut demander le résumé IA."}, status_code=403)
    transcription = session.exec(
        select(TranscriptionSeance).where(TranscriptionSeance.seance_id == seance_id)
    ).first()
    if not transcription or not transcription.contenu:
        return JSONResponse({"erreur": "Enregistre d'abord la transcription."}, status_code=409)
    try:
        resume = classe_transcription.resumer_transcription(
            contenu=transcription.contenu,
            nom_cours=cours.nom,
        )
    except RuntimeError as erreur:
        return JSONResponse({"erreur": str(erreur)}, status_code=503)
    except ValueError as erreur:
        return JSONResponse({"erreur": str(erreur)}, status_code=422)
    transcription.resume_ia = resume
    transcription.date_modification = datetime.utcnow()
    session.add(transcription)
    session.commit()
    return JSONResponse({"ok": True, "resume": resume})
