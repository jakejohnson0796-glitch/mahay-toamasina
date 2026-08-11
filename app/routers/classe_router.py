"""
Classe virtuelle : cours animes par un professeur, avec des seances que
les etudiants inscrits rejoignent. Modelise sur le meme schema que les
cercles d'etude (createur/proprietaire + inscription + gestion des
membres) — voir cercles_router.py pour le pattern d'origine.

Cette premiere passe couvre la structure (cours, inscriptions, seances,
presence) SANS la salle audio/video LiveKit elle-meme : la route
rejoindre_seance() enregistre deja la presence et redirige vers une page
de salle, mais cette page est un ecran d'attente tant que l'integration
LiveKit (jeton, connexion WebRTC, tableau blanc) n'est pas branchee —
prochaine etape explicitement separee de celle-ci.
"""
import secrets
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse
from sqlmodel import Session, select

from ..database import get_session, engine
from ..templating import templates
from ..csrf import verifier_csrf
from ..models import Cours, InscriptionCours, Seance, StatutSeance, PresenceSeance, Utilisateur, RoleUtilisateur, EvenementTableauBlanc, TypeEvenementTableau, AutorisationEcritureTableau, Devoir, RenduDevoir
from ..auth import utilisateur_courant
from ..livekit_tokens import generer_jeton_salle, livekit_configure, LiveKitNonConfigure
from ..config import parametres
from ..ws_manager import gestionnaire
from ..storage import sauvegarder_fichier, obtenir_url_telechargement, stockage_distant_actif, FichierInvalide

router = APIRouter()


def _est_professeur(utilisateur: Optional[Utilisateur]) -> bool:
    return bool(utilisateur and utilisateur.role in (RoleUtilisateur.PROFESSEUR, RoleUtilisateur.ADMIN))


def _peut_gerer_cours(cours: Cours, utilisateur: Optional[Utilisateur]) -> bool:
    """Professeur proprietaire de CE cours (uniquement le sien) ou admin.
    Reverifie a chaque appel de route, jamais fait confiance a
    l'interface — meme principe que _peut_gerer_cercle dans
    cercles_router.py."""
    if not utilisateur:
        return False
    return utilisateur.id == cours.professeur_id or utilisateur.role == RoleUtilisateur.ADMIN


def _est_inscrit(session: Session, cours_id: int, utilisateur_id: int) -> bool:
    return session.exec(
        select(InscriptionCours).where(
            InscriptionCours.cours_id == cours_id,
            InscriptionCours.utilisateur_id == utilisateur_id,
        )
    ).first() is not None


def _generer_nom_salle(cours_id: int) -> str:
    # Prefixe lisible (utile en debug/logs LiveKit) + suffixe aleatoire
    # non devinable (defense en profondeur : meme si l'autorisation
    # d'acces est de toute facon revalidee par le jeton LiveKit signe
    # cote serveur, un nom de salle non predictible evite les tentatives
    # de connexion directe au hasard).
    return f"mahay-cours{cours_id}-{secrets.token_hex(6)}"


def _peut_ecrire_tableau(session: Session, seance_id: int, cours: Cours, utilisateur: Utilisateur) -> bool:
    """Le prof proprietaire du cours (ou un admin) peut toujours ecrire.
    Un etudiant ne peut ecrire QUE s'il a ete explicitement autorise pour
    CETTE seance precise (voir AutorisationEcritureTableau) — verifie a
    chaque evenement recu sur le WebSocket, jamais fait confiance a
    l'etat affiche cote client (qui pourrait etre bidouille)."""
    if _peut_gerer_cours(cours, utilisateur):
        return True
    return session.exec(
        select(AutorisationEcritureTableau).where(
            AutorisationEcritureTableau.seance_id == seance_id,
            AutorisationEcritureTableau.utilisateur_id == utilisateur.id,
        )
    ).first() is not None


def _reconstituer_etat_tableau(session: Session, seance_id: int) -> list:
    """Rejoue le journal d'evenements dans l'ordre pour reconstituer
    l'etat VISIBLE actuel du tableau (necessaire pour qu'un etudiant qui
    rejoint en retard voie le tableau tel qu'il est, pas juste les
    evenements a partir de sa connexion). Voir EvenementTableauBlanc
    pour l'explication complete de cette approche append-only."""
    evenements = session.exec(
        select(EvenementTableauBlanc)
        .where(EvenementTableauBlanc.seance_id == seance_id)
        .order_by(EvenementTableauBlanc.date_creation)
    ).all()

    etat: dict = {}
    for e in evenements:
        if e.type_evenement == TypeEvenementTableau.EFFACER_TOUT:
            etat = {}
        elif e.type_evenement == TypeEvenementTableau.SUPPRESSION:
            etat.pop(e.element_id, None)
        else:
            etat[e.element_id] = {
                "type": e.type_evenement.value,
                "element_id": e.element_id,
                "utilisateur_id": e.utilisateur_id,
                "donnees": json.loads(e.donnees),
            }
    return list(etat.values())


@router.get("/classe")
def liste_cours(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    if utilisateur.role in (RoleUtilisateur.PROFESSEUR, RoleUtilisateur.ADMIN):
        if utilisateur.role == RoleUtilisateur.ADMIN:
            cours_visibles = session.exec(select(Cours).order_by(Cours.date_creation.desc())).all()
        else:
            cours_visibles = session.exec(
                select(Cours).where(Cours.professeur_id == utilisateur.id).order_by(Cours.date_creation.desc())
            ).all()
    else:
        lignes = session.exec(
            select(Cours)
            .where(InscriptionCours.cours_id == Cours.id)
            .where(InscriptionCours.utilisateur_id == utilisateur.id)
            .order_by(Cours.date_creation.desc())
        ).all()
        cours_visibles = lignes

    return templates.TemplateResponse(
        request,
        "classe_liste.html",
        {"utilisateur": utilisateur, "cours_visibles": cours_visibles, "est_professeur": _est_professeur(utilisateur)},
    )


@router.post("/classe/creer")
def creer_cours(
    request: Request,
    nom: str = Form(...),
    matiere: str = Form(...),
    niveau: str = Form(...),
    description: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not _est_professeur(utilisateur):
        return RedirectResponse("/classe", status_code=303)

    cours = Cours(nom=nom, matiere=matiere, niveau=niveau, description=description or None, professeur_id=utilisateur.id)
    session.add(cours)
    session.commit()
    session.refresh(cours)

    return RedirectResponse(f"/classe/{cours.id}", status_code=303)


@router.get("/classe/{cours_id}")
def detail_cours(request: Request, cours_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cours = session.get(Cours, cours_id)
    if not cours:
        return RedirectResponse("/classe", status_code=303)

    peut_gerer = _peut_gerer_cours(cours, utilisateur)
    inscrit = _est_inscrit(session, cours_id, utilisateur.id)

    if not peut_gerer and not inscrit:
        return RedirectResponse("/classe", status_code=303)

    professeur = session.get(Utilisateur, cours.professeur_id)
    seances = session.exec(
        select(Seance).where(Seance.cours_id == cours_id).order_by(Seance.date_creation)
    ).all()
    nb_etudiants = len(session.exec(select(InscriptionCours).where(InscriptionCours.cours_id == cours_id)).all())
    devoirs = session.exec(
        select(Devoir).where(Devoir.cours_id == cours_id).order_by(Devoir.date_creation.desc())
    ).all()

    mes_rendus_ids = set()
    if not peut_gerer and devoirs:
        mes_rendus = session.exec(
            select(RenduDevoir.devoir_id).where(
                RenduDevoir.utilisateur_id == utilisateur.id,
                RenduDevoir.devoir_id.in_([d.id for d in devoirs]),
            )
        ).all()
        mes_rendus_ids = set(mes_rendus)

    return templates.TemplateResponse(
        request,
        "classe_detail.html",
        {
            "utilisateur": utilisateur,
            "cours": cours,
            "professeur": professeur,
            "seances": seances,
            "nb_etudiants": nb_etudiants,
            "peut_gerer": peut_gerer,
            "devoirs": devoirs,
            "mes_rendus_ids": mes_rendus_ids,
        },
    )


@router.get("/classe/{cours_id}/etudiants")
def liste_etudiants_cours(request: Request, cours_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cours = session.get(Cours, cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur):
        return RedirectResponse(f"/classe/{cours_id}", status_code=303)

    lignes = session.exec(
        select(InscriptionCours, Utilisateur)
        .where(InscriptionCours.cours_id == cours_id)
        .where(InscriptionCours.utilisateur_id == Utilisateur.id)
        .order_by(InscriptionCours.date_inscription)
    ).all()
    inscriptions = [{"inscription": i, "utilisateur": u} for i, u in lignes]

    return templates.TemplateResponse(
        request,
        "classe_etudiants.html",
        {"utilisateur": utilisateur, "cours": cours, "inscriptions": inscriptions},
    )


@router.post("/classe/{cours_id}/etudiants/ajouter")
def ajouter_etudiant(
    request: Request,
    cours_id: int,
    telephone: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cours = session.get(Cours, cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur):
        return RedirectResponse(f"/classe/{cours_id}", status_code=303)

    cible = session.exec(select(Utilisateur).where(Utilisateur.telephone == telephone.strip())).first()
    if not cible:
        return RedirectResponse(f"/classe/{cours_id}/etudiants?erreur=utilisateur_introuvable", status_code=303)

    if not _est_inscrit(session, cours_id, cible.id):
        session.add(InscriptionCours(cours_id=cours_id, utilisateur_id=cible.id))
        session.commit()

    return RedirectResponse(f"/classe/{cours_id}/etudiants?ajoute=1", status_code=303)


@router.post("/classe/{cours_id}/etudiants/{utilisateur_id}/retirer")
def retirer_etudiant(request: Request, cours_id: int, utilisateur_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cours = session.get(Cours, cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur):
        return RedirectResponse(f"/classe/{cours_id}", status_code=303)

    inscription = session.exec(
        select(InscriptionCours).where(
            InscriptionCours.cours_id == cours_id,
            InscriptionCours.utilisateur_id == utilisateur_id,
        )
    ).first()
    if inscription:
        session.delete(inscription)
        session.commit()

    return RedirectResponse(f"/classe/{cours_id}/etudiants", status_code=303)


@router.post("/classe/{cours_id}/seances/creer")
def creer_seance(
    request: Request,
    cours_id: int,
    titre: str = Form(...),
    description: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cours = session.get(Cours, cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur):
        return RedirectResponse(f"/classe/{cours_id}", status_code=303)

    seance = Seance(cours_id=cours_id, titre=titre, description=description or None, nom_salle_livekit=_generer_nom_salle(cours_id))
    session.add(seance)
    session.commit()

    return RedirectResponse(f"/classe/{cours_id}", status_code=303)


@router.post("/classe/seances/{seance_id}/demarrer")
def demarrer_seance(request: Request, seance_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, seance.cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur):
        return RedirectResponse(f"/classe/{seance.cours_id}", status_code=303)

    if seance.statut == StatutSeance.PLANIFIEE:
        seance.statut = StatutSeance.EN_COURS
        seance.date_debut_reelle = datetime.utcnow()
        session.add(seance)
        session.commit()

    return RedirectResponse(f"/classe/{cours.id}", status_code=303)


@router.post("/classe/seances/{seance_id}/terminer")
def terminer_seance(request: Request, seance_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, seance.cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur):
        return RedirectResponse(f"/classe/{seance.cours_id}", status_code=303)

    if seance.statut == StatutSeance.EN_COURS:
        seance.statut = StatutSeance.TERMINEE
        seance.date_fin_reelle = datetime.utcnow()
        session.add(seance)

        # Cloture toutes les presences encore ouvertes (participants qui
        # n'ont jamais explicitement "quitte" avant la fin de seance).
        maintenant = datetime.utcnow()
        presences_ouvertes = session.exec(
            select(PresenceSeance).where(PresenceSeance.seance_id == seance_id, PresenceSeance.heure_sortie == None)  # noqa: E711
        ).all()
        for p in presences_ouvertes:
            delta = (maintenant - p.heure_entree).total_seconds()
            p.duree_estimee_secondes += int(delta)
            p.heure_sortie = maintenant
            session.add(p)

        session.commit()

    return RedirectResponse(f"/classe/{cours.id}", status_code=303)


@router.post("/classe/seances/{seance_id}/rejoindre")
def rejoindre_seance(request: Request, seance_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, seance.cours_id)
    if not cours:
        return RedirectResponse("/classe", status_code=303)

    peut_gerer = _peut_gerer_cours(cours, utilisateur)
    if not peut_gerer and not _est_inscrit(session, cours.id, utilisateur.id):
        return RedirectResponse(f"/classe/{cours.id}", status_code=303)

    if seance.statut != StatutSeance.EN_COURS:
        return RedirectResponse(f"/classe/{cours.id}?erreur=seance_non_demarree", status_code=303)

    # Nouvelle ligne de presence a chaque "rejoindre" (permet de mesurer
    # plusieurs allers-retours dans la meme seance) — voir terminer_seance
    # et quitter_seance pour la fermeture/le cumul de duree.
    session.add(PresenceSeance(seance_id=seance_id, utilisateur_id=utilisateur.id))
    session.commit()

    return RedirectResponse(f"/classe/seances/{seance_id}/salle", status_code=303)


@router.get("/classe/seances/{seance_id}/salle")
def salle_virtuelle(request: Request, seance_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, seance.cours_id)
    if not cours:
        return RedirectResponse("/classe", status_code=303)

    peut_gerer = _peut_gerer_cours(cours, utilisateur)
    if not peut_gerer and not _est_inscrit(session, cours.id, utilisateur.id):
        return RedirectResponse(f"/classe/{cours.id}", status_code=303)

    if seance.statut != StatutSeance.EN_COURS:
        return RedirectResponse(f"/classe/{cours.id}?erreur=seance_non_demarree", status_code=303)

    if not livekit_configure():
        return templates.TemplateResponse(
            request,
            "classe_salle.html",
            {
                "utilisateur": utilisateur, "cours": cours, "seance": seance, "peut_gerer": peut_gerer,
                "erreur_livekit": "La classe virtuelle audio/video n'est pas encore configuree sur ce serveur (variables LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET manquantes).",
                "jeton_livekit": None, "url_livekit": None,
            },
        )

    try:
        jeton_livekit = generer_jeton_salle(
            nom_salle=seance.nom_salle_livekit,
            utilisateur_id=utilisateur.id,
            nom_affiche=utilisateur.nom,
            peut_publier=True,
            peut_partager_ecran=peut_gerer,
        )
    except LiveKitNonConfigure as erreur:
        return templates.TemplateResponse(
            request,
            "classe_salle.html",
            {
                "utilisateur": utilisateur, "cours": cours, "seance": seance, "peut_gerer": peut_gerer,
                "erreur_livekit": str(erreur), "jeton_livekit": None, "url_livekit": None,
            },
        )

    return templates.TemplateResponse(
        request,
        "classe_salle.html",
        {
            "utilisateur": utilisateur, "cours": cours, "seance": seance, "peut_gerer": peut_gerer,
            "erreur_livekit": None, "jeton_livekit": jeton_livekit, "url_livekit": parametres.livekit_url,
        },
    )


@router.post("/classe/seances/{seance_id}/quitter")
def quitter_seance(request: Request, seance_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303)

    presence = session.exec(
        select(PresenceSeance)
        .where(PresenceSeance.seance_id == seance_id)
        .where(PresenceSeance.utilisateur_id == utilisateur.id)
        .where(PresenceSeance.heure_sortie == None)  # noqa: E711
        .order_by(PresenceSeance.heure_entree.desc())
    ).first()
    if presence:
        maintenant = datetime.utcnow()
        presence.duree_estimee_secondes += int((maintenant - presence.heure_entree).total_seconds())
        presence.heure_sortie = maintenant
        session.add(presence)
        session.commit()

    return RedirectResponse(f"/classe/{seance.cours_id}", status_code=303)


@router.get("/classe/seances/{seance_id}/presences")
def voir_presences(request: Request, seance_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, seance.cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur):
        return RedirectResponse(f"/classe/{seance.cours_id if cours else ''}", status_code=303)

    lignes = session.exec(
        select(PresenceSeance, Utilisateur)
        .where(PresenceSeance.seance_id == seance_id)
        .where(PresenceSeance.utilisateur_id == Utilisateur.id)
        .order_by(PresenceSeance.heure_entree)
    ).all()
    presences = [{"presence": p, "utilisateur": u} for p, u in lignes]

    return templates.TemplateResponse(
        request,
        "classe_presences.html",
        {"utilisateur": utilisateur, "cours": cours, "seance": seance, "presences": presences},
    )


@router.get("/classe/seances/{seance_id}/tableau")
def page_tableau(request: Request, seance_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, seance.cours_id)
    if not cours:
        return RedirectResponse("/classe", status_code=303)

    peut_gerer = _peut_gerer_cours(cours, utilisateur)
    if not peut_gerer and not _est_inscrit(session, cours.id, utilisateur.id):
        return RedirectResponse(f"/classe/{cours.id}", status_code=303)

    etat_initial = _reconstituer_etat_tableau(session, seance_id)

    autorises = []
    if peut_gerer:
        lignes = session.exec(
            select(AutorisationEcritureTableau, Utilisateur)
            .where(AutorisationEcritureTableau.seance_id == seance_id)
            .where(AutorisationEcritureTableau.utilisateur_id == Utilisateur.id)
        ).all()
        autorises = [{"utilisateur_id": u.id, "nom": u.nom} for _, u in lignes]

        # Liste des inscrits pour le menu "autoriser quelqu'un" — exclut
        # ceux deja autorises pour ne pas les proposer deux fois.
        deja_autorises_ids = {a["utilisateur_id"] for a in autorises}
        lignes_inscrits = session.exec(
            select(InscriptionCours, Utilisateur)
            .where(InscriptionCours.cours_id == cours.id)
            .where(InscriptionCours.utilisateur_id == Utilisateur.id)
        ).all()
        inscrits_non_autorises = [
            {"utilisateur_id": u.id, "nom": u.nom} for _, u in lignes_inscrits if u.id not in deja_autorises_ids
        ]
    else:
        inscrits_non_autorises = []

    peut_ecrire = _peut_ecrire_tableau(session, seance_id, cours, utilisateur)

    return templates.TemplateResponse(
        request,
        "classe_tableau.html",
        {
            "utilisateur": utilisateur, "cours": cours, "seance": seance,
            "peut_gerer": peut_gerer, "peut_ecrire": peut_ecrire,
            "etat_initial_json": json.dumps(etat_initial),
            "autorises": autorises, "inscrits_non_autorises": inscrits_non_autorises,
        },
    )


@router.post("/classe/seances/{seance_id}/tableau/autoriser/{utilisateur_id}")
async def autoriser_ecriture_tableau(request: Request, seance_id: int, utilisateur_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, seance.cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur):
        return RedirectResponse(f"/classe/{seance.cours_id if cours else ''}", status_code=303)

    if not _est_inscrit(session, cours.id, utilisateur_id):
        return RedirectResponse(f"/classe/seances/{seance_id}/tableau", status_code=303)

    deja = session.exec(
        select(AutorisationEcritureTableau).where(
            AutorisationEcritureTableau.seance_id == seance_id,
            AutorisationEcritureTableau.utilisateur_id == utilisateur_id,
        )
    ).first()
    if not deja:
        session.add(AutorisationEcritureTableau(seance_id=seance_id, utilisateur_id=utilisateur_id))
        session.commit()

    # Informe en temps reel le concerne (et tout le monde, pour mettre a
    # jour l'affichage "qui peut ecrire" cote prof) sans qu'il ait besoin
    # de recharger la page.
    await gestionnaire.diffuser(f"tableau-{seance_id}", {"type": "permission", "utilisateur_id": utilisateur_id, "autorise": True})

    return RedirectResponse(f"/classe/seances/{seance_id}/tableau", status_code=303)


@router.post("/classe/seances/{seance_id}/tableau/revoquer/{utilisateur_id}")
async def revoquer_ecriture_tableau(request: Request, seance_id: int, utilisateur_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, seance.cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur):
        return RedirectResponse(f"/classe/{seance.cours_id if cours else ''}", status_code=303)

    autorisation = session.exec(
        select(AutorisationEcritureTableau).where(
            AutorisationEcritureTableau.seance_id == seance_id,
            AutorisationEcritureTableau.utilisateur_id == utilisateur_id,
        )
    ).first()
    if autorisation:
        session.delete(autorisation)
        session.commit()

    await gestionnaire.diffuser(f"tableau-{seance_id}", {"type": "permission", "utilisateur_id": utilisateur_id, "autorise": False})

    return RedirectResponse(f"/classe/seances/{seance_id}/tableau", status_code=303)


@router.websocket("/classe/seances/{seance_id}/tableau/ws")
async def tableau_ws(websocket: WebSocket, seance_id: int):
    """Synchronisation temps reel du tableau blanc. Reutilise le meme
    gestionnaire de connexions que le chat des cercles (app/ws_manager.py),
    avec une cle de salle distincte ("tableau-{id}") pour ne jamais se
    melanger avec les salons de cercles d'etude qui partagent le meme
    objet gestionnaire.

    Chaque evenement recu est REVALIDE cote serveur avant d'etre persiste
    et diffuse (type reconnu, permission d'ecriture a l'instant present —
    pas seulement a la connexion, puisqu'elle peut etre revoquee en
    cours de route) : un client qui bidouillerait son JS ne peut pas
    dessiner sans autorisation reelle, seulement casser sa propre
    experience locale."""
    with Session(engine) as session:
        user_id = websocket.session.get("user_id")
        if not user_id:
            await websocket.close(code=4401)
            return

        utilisateur = session.get(Utilisateur, user_id)
        if not utilisateur:
            await websocket.close(code=4401)
            return

        seance = session.get(Seance, seance_id)
        if not seance:
            await websocket.close(code=4404)
            return
        cours = session.get(Cours, seance.cours_id)
        if not cours:
            await websocket.close(code=4404)
            return

        peut_gerer = _peut_gerer_cours(cours, utilisateur)
        if not peut_gerer and not _est_inscrit(session, cours.id, utilisateur.id):
            await websocket.close(code=4403)
            return

        cle_salle = f"tableau-{seance_id}"
        await gestionnaire.connecter(cle_salle, websocket, utilisateur.id, utilisateur.nom)

        try:
            while True:
                brut = await websocket.receive_json()
                type_evt = brut.get("type")

                if type_evt not in ("trait", "forme", "texte", "suppression", "effacer_tout"):
                    continue  # type inconnu, ignore silencieusement

                # Revalidation de permission a CHAQUE evenement (pas
                # seulement a la connexion) : une autorisation revoquee
                # entre-temps doit bloquer immediatement, pas seulement
                # apres une reconnexion.
                with Session(engine) as session_fraiche:
                    if not _peut_ecrire_tableau(session_fraiche, seance_id, cours, utilisateur):
                        continue

                    if type_evt == "effacer_tout" and not peut_gerer:
                        # Effacer TOUT le tableau reste reserve au
                        # prof/admin, meme pour un etudiant autorise a
                        # dessiner — un etudiant autorise peut ajouter et
                        # annuler SES PROPRES traits, pas rayer le travail
                        # de tout le monde.
                        continue

                    element_id = str(brut.get("element_id", ""))[:100]
                    if not element_id:
                        continue

                    if type_evt == "suppression":
                        # Un etudiant ne peut supprimer QUE ses propres
                        # elements ; le prof/admin peut supprimer
                        # n'importe lequel (moderation).
                        if not peut_gerer:
                            evenement_original = session_fraiche.exec(
                                select(EvenementTableauBlanc)
                                .where(EvenementTableauBlanc.seance_id == seance_id)
                                .where(EvenementTableauBlanc.element_id == element_id)
                                .where(EvenementTableauBlanc.type_evenement != TypeEvenementTableau.SUPPRESSION)
                                .order_by(EvenementTableauBlanc.date_creation.desc())
                            ).first()
                            if not evenement_original or evenement_original.utilisateur_id != utilisateur.id:
                                continue

                    donnees = brut.get("donnees", {})
                    try:
                        donnees_json = json.dumps(donnees)[:20000]  # borne la taille d'un evenement
                    except (TypeError, ValueError):
                        continue

                    evenement = EvenementTableauBlanc(
                        seance_id=seance_id,
                        utilisateur_id=utilisateur.id,
                        type_evenement=TypeEvenementTableau(type_evt),
                        element_id=element_id,
                        donnees=donnees_json,
                    )
                    session_fraiche.add(evenement)
                    session_fraiche.commit()

                await gestionnaire.diffuser(cle_salle, {
                    "type": type_evt,
                    "element_id": element_id,
                    "utilisateur_id": utilisateur.id,
                    "donnees": donnees,
                })
        except WebSocketDisconnect:
            pass
        finally:
            gestionnaire.deconnecter(cle_salle, websocket)


# ============================================================
# Devoirs & rendus
# ============================================================

@router.post("/classe/{cours_id}/devoirs/creer")
def creer_devoir(
    request: Request,
    cours_id: int,
    titre: str = Form(...),
    description: Optional[str] = Form(None),
    date_limite: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cours = session.get(Cours, cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur):
        return RedirectResponse(f"/classe/{cours_id}", status_code=303)

    date_limite_parsee = None
    if date_limite:
        try:
            date_limite_parsee = datetime.fromisoformat(date_limite)
        except ValueError:
            date_limite_parsee = None

    devoir = Devoir(cours_id=cours_id, titre=titre, description=description or None, date_limite=date_limite_parsee)
    session.add(devoir)
    session.commit()

    return RedirectResponse(f"/classe/{cours_id}", status_code=303)


@router.get("/classe/devoirs/{devoir_id}")
def detail_devoir(request: Request, devoir_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    devoir = session.get(Devoir, devoir_id)
    if not devoir:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, devoir.cours_id)
    if not cours:
        return RedirectResponse("/classe", status_code=303)

    peut_gerer = _peut_gerer_cours(cours, utilisateur)
    if not peut_gerer and not _est_inscrit(session, cours.id, utilisateur.id):
        return RedirectResponse(f"/classe/{cours.id}", status_code=303)

    delai_depasse = bool(devoir.date_limite and datetime.utcnow() > devoir.date_limite)

    mon_rendu = None
    if not peut_gerer:
        mon_rendu = session.exec(
            select(RenduDevoir).where(RenduDevoir.devoir_id == devoir_id, RenduDevoir.utilisateur_id == utilisateur.id)
        ).first()

    rendus = []
    if peut_gerer:
        lignes = session.exec(
            select(RenduDevoir, Utilisateur)
            .where(RenduDevoir.devoir_id == devoir_id)
            .where(RenduDevoir.utilisateur_id == Utilisateur.id)
            .order_by(RenduDevoir.date_rendu.desc())
        ).all()
        rendus = [{"rendu": r, "utilisateur": u} for r, u in lignes]

    return templates.TemplateResponse(
        request,
        "classe_devoir.html",
        {
            "utilisateur": utilisateur, "cours": cours, "devoir": devoir, "peut_gerer": peut_gerer,
            "delai_depasse": delai_depasse, "mon_rendu": mon_rendu, "rendus": rendus,
        },
    )


@router.post("/classe/devoirs/{devoir_id}/rendre")
def rendre_devoir(
    request: Request,
    devoir_id: int,
    commentaire: Optional[str] = Form(None),
    fichier: UploadFile = File(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    devoir = session.get(Devoir, devoir_id)
    if not devoir:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, devoir.cours_id)
    if not cours:
        return RedirectResponse("/classe", status_code=303)

    # Rendre un devoir est reserve aux etudiants inscrits — un
    # professeur/admin gere le devoir, il ne "rend" pas de copie.
    if not _est_inscrit(session, cours.id, utilisateur.id):
        return RedirectResponse(f"/classe/{cours.id}", status_code=303)

    if devoir.date_limite and datetime.utcnow() > devoir.date_limite:
        return RedirectResponse(f"/classe/devoirs/{devoir_id}?erreur=delai_depasse", status_code=303)

    reference = f"devoir{devoir_id}_etu{utilisateur.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    try:
        chemin_stocke = sauvegarder_fichier(fichier, reference)
    except FichierInvalide as erreur:
        return RedirectResponse(f"/classe/devoirs/{devoir_id}?erreur=fichier_invalide", status_code=303)

    # Un seul rendu "vivant" par etudiant : un nouveau depot ecrase le
    # precedent (mais garde le meme enregistrement, donc perd la note
    # deja donnee si l'etudiant re-rend apres correction — comportement
    # voulu : la nouvelle copie doit etre re-corrigee, pas heriter d'une
    # note qui ne correspond plus au contenu rendu).
    rendu_existant = session.exec(
        select(RenduDevoir).where(RenduDevoir.devoir_id == devoir_id, RenduDevoir.utilisateur_id == utilisateur.id)
    ).first()
    if rendu_existant:
        rendu_existant.chemin_fichier = chemin_stocke
        rendu_existant.nom_fichier_original = fichier.filename or "rendu"
        rendu_existant.commentaire = commentaire or None
        rendu_existant.date_rendu = datetime.utcnow()
        rendu_existant.note = None
        rendu_existant.appreciation_prof = None
        rendu_existant.date_correction = None
        session.add(rendu_existant)
    else:
        session.add(RenduDevoir(
            devoir_id=devoir_id, utilisateur_id=utilisateur.id, chemin_fichier=chemin_stocke,
            nom_fichier_original=fichier.filename or "rendu", commentaire=commentaire or None,
        ))
    session.commit()

    return RedirectResponse(f"/classe/devoirs/{devoir_id}?rendu=1", status_code=303)


@router.get("/classe/devoirs/rendus/{rendu_id}/telecharger")
def telecharger_rendu(request: Request, rendu_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    rendu = session.get(RenduDevoir, rendu_id)
    if not rendu:
        return RedirectResponse("/classe", status_code=303)
    devoir = session.get(Devoir, rendu.devoir_id)
    cours = session.get(Cours, devoir.cours_id) if devoir else None
    if not devoir or not cours:
        return RedirectResponse("/classe", status_code=303)

    # Le prof/admin du cours peut telecharger n'importe quel rendu ;
    # l'etudiant peut seulement telecharger LE SIEN (jamais celui d'un
    # camarade, meme en devinant l'id).
    peut_gerer = _peut_gerer_cours(cours, utilisateur)
    if not peut_gerer and rendu.utilisateur_id != utilisateur.id:
        return RedirectResponse(f"/classe/{cours.id}", status_code=303)

    if stockage_distant_actif():
        return RedirectResponse(obtenir_url_telechargement(rendu.chemin_fichier))
    return FileResponse(rendu.chemin_fichier, filename=rendu.nom_fichier_original)


@router.post("/classe/devoirs/rendus/{rendu_id}/noter")
def noter_rendu(
    request: Request,
    rendu_id: int,
    note: Optional[str] = Form(None),
    appreciation_prof: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    rendu = session.get(RenduDevoir, rendu_id)
    if not rendu:
        return RedirectResponse("/classe", status_code=303)
    devoir = session.get(Devoir, rendu.devoir_id)
    cours = session.get(Cours, devoir.cours_id) if devoir else None
    if not devoir or not cours or not _peut_gerer_cours(cours, utilisateur):
        return RedirectResponse(f"/classe/{cours.id if cours else ''}", status_code=303)

    note_validee = None
    if note:
        try:
            note_validee = max(0.0, min(20.0, float(note)))
        except ValueError:
            note_validee = None

    rendu.note = note_validee
    rendu.appreciation_prof = appreciation_prof or None
    rendu.date_correction = datetime.utcnow()
    session.add(rendu)
    session.commit()

    return RedirectResponse(f"/classe/devoirs/{devoir.id}", status_code=303)
