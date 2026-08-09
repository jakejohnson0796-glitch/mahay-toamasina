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
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..models import Cours, InscriptionCours, Seance, StatutSeance, PresenceSeance, Utilisateur, RoleUtilisateur
from ..auth import utilisateur_courant
from ..livekit_tokens import generer_jeton_salle, livekit_configure, LiveKitNonConfigure
from ..config import parametres

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
