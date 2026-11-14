"""Annuaire privé des répétiteurs vérifiés et demandes d'accompagnement.

Les coordonnées privées des comptes ne sont jamais incluses dans les vues.
Les échanges sont limités à une demande scolaire structurée et à son statut.
"""
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_
from sqlmodel import Session, select

from ..auth import utilisateur_courant
from ..csrf import verifier_csrf
from ..database import get_session
from ..models import DemandeAccompagnement, RoleUtilisateur, Utilisateur
from ..templating import templates


router = APIRouter()

STATUT_EN_ATTENTE = "en_attente"
STATUT_ACCEPTEE = "acceptee"
STATUT_REFUSEE = "refusee"
MAX_DEMANDES_EN_ATTENTE = 5
LONGUEUR_MAX_MESSAGE = 800

# Interdit les coordonnées directes et liens dans les premiers échanges :
# la demande reste dans MITARIDALA et ne révèle pas les numéros des comptes.
_CONTACT_INTERDIT = re.compile(
    r"(?:https?://|www\\.|[\\w.+-]+@[\\w.-]+\\.[A-Za-z]{2,}|"
    r"(?:\\+?261|0)\\s*(?:32|33|34|38)(?:[\\s.-]?\\d){7}\\b)",
    re.IGNORECASE,
)


def nom_public_repetiteur(nom: str) -> str:
    """Affiche un prénom et l'initiale du nom, jamais les coordonnées du compte."""
    morceaux = [part for part in (nom or "").strip().split() if part]
    if not morceaux:
        return "Répétiteur vérifié"
    if len(morceaux) == 1:
        return morceaux[0]
    return f"{morceaux[0]} {morceaux[-1][0].upper()}."


def _est_etudiant(utilisateur: Optional[Utilisateur]) -> bool:
    return bool(utilisateur and utilisateur.role == RoleUtilisateur.ETUDIANT)


def _est_repetiteur_verifie(utilisateur: Optional[Utilisateur]) -> bool:
    return bool(
        utilisateur
        and utilisateur.est_actif
        and utilisateur.role == RoleUtilisateur.REPETITEUR
        and utilisateur.statut_verification_repetiteur == "approuve"
    )


def _contenu_public_sans_contact(valeur: Optional[str]) -> str:
    texte = " ".join((valeur or "").split())
    if _CONTACT_INTERDIT.search(texte):
        return "Une partie de cette présentation a été masquée pour protéger les coordonnées personnelles."
    return texte[:1000]


def _profil_public(utilisateur: Utilisateur) -> dict:
    """Projection en liste blanche : pas de téléphone, email, identifiant ni ID public."""
    return {
        "id": utilisateur.id,
        "nom": nom_public_repetiteur(utilisateur.nom),
        "matieres": _contenu_public_sans_contact(utilisateur.matieres_repetiteur),
        "niveaux": _contenu_public_sans_contact(utilisateur.niveaux_repetiteur),
        "tarif": utilisateur.tarif_horaire_repetiteur_ariary,
        "presentation": _contenu_public_sans_contact(utilisateur.bio),
    }


@router.get("/repetiteurs")
def annuaire_repetiteurs(
    request: Request,
    q: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """Annuaire visible uniquement par les comptes élèves connectés."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    if not _est_etudiant(utilisateur):
        return RedirectResponse("/dashboard", status_code=303)

    recherche = " ".join((q or "").split())[:100]
    requete = select(Utilisateur).where(
        Utilisateur.role == RoleUtilisateur.REPETITEUR,
        Utilisateur.statut_verification_repetiteur == "approuve",
        Utilisateur.est_actif.is_(True),
        Utilisateur.matieres_repetiteur.is_not(None),
        Utilisateur.niveaux_repetiteur.is_not(None),
    )
    if recherche:
        motif = f"%{recherche.casefold()}%"
        requete = requete.where(
            or_(
                func.lower(Utilisateur.matieres_repetiteur).like(motif),
                func.lower(Utilisateur.niveaux_repetiteur).like(motif),
                func.lower(Utilisateur.bio).like(motif),
            )
        )

    profils = session.exec(requete.order_by(Utilisateur.nom).limit(60)).all()
    demandes_en_attente = session.exec(
        select(DemandeAccompagnement).where(
            DemandeAccompagnement.etudiant_id == utilisateur.id,
            DemandeAccompagnement.statut == STATUT_EN_ATTENTE,
        )
    ).all()
    repetiteurs_en_attente = {demande.repetiteur_id for demande in demandes_en_attente}

    return templates.TemplateResponse(
        request,
        "repetiteurs.html",
        {
            "utilisateur": utilisateur,
            "repetiteurs": [
                {**_profil_public(profil), "demande_en_attente": profil.id in repetiteurs_en_attente}
                for profil in profils
            ],
            "recherche": recherche,
        },
    )


@router.post("/repetiteurs/{repetiteur_id}/demande")
def creer_demande_accompagnement(
    request: Request,
    repetiteur_id: int,
    matiere: str = Form(""),
    niveau: str = Form(""),
    message: str = Form(""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Crée une demande scolaire sans échanger de téléphone ou d'email."""
    etudiant = utilisateur_courant(request, session)
    if not etudiant:
        return RedirectResponse("/connexion", status_code=303)
    if not _est_etudiant(etudiant):
        return RedirectResponse("/dashboard", status_code=303)

    repetiteur = session.get(Utilisateur, repetiteur_id)
    if not _est_repetiteur_verifie(repetiteur) or repetiteur.id == etudiant.id:
        return RedirectResponse("/repetiteurs?erreur=profil_indisponible", status_code=303)

    matiere = " ".join((matiere or "").split())[:120]
    niveau = " ".join((niveau or "").split())[:120]
    message = " ".join((message or "").split())
    if not (2 <= len(matiere) <= 120 and 1 <= len(niveau) <= 120 and 10 <= len(message) <= LONGUEUR_MAX_MESSAGE):
        return RedirectResponse("/repetiteurs?erreur=champs_invalides", status_code=303)
    if _CONTACT_INTERDIT.search(" ".join((matiere, niveau, message))):
        return RedirectResponse("/repetiteurs?erreur=coordonnees_interdites", status_code=303)

    demandes_actives = session.exec(
        select(DemandeAccompagnement).where(
            DemandeAccompagnement.etudiant_id == etudiant.id,
            DemandeAccompagnement.statut == STATUT_EN_ATTENTE,
        )
    ).all()
    if any(demande.repetiteur_id == repetiteur.id for demande in demandes_actives):
        return RedirectResponse("/repetiteurs?erreur=demande_existante", status_code=303)
    if len(demandes_actives) >= MAX_DEMANDES_EN_ATTENTE:
        return RedirectResponse("/repetiteurs?erreur=limite_demandes", status_code=303)

    demande = DemandeAccompagnement(
        etudiant_id=etudiant.id,
        repetiteur_id=repetiteur.id,
        matiere=matiere,
        niveau=niveau,
        message=message,
        statut=STATUT_EN_ATTENTE,
        date_creation=datetime.utcnow(),
    )
    session.add(demande)
    session.commit()
    return RedirectResponse("/mes-demandes-repetiteur?ok=demande_envoyee", status_code=303)


@router.get("/mes-demandes-repetiteur")
def mes_demandes_repetiteur(
    request: Request,
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    if not _est_etudiant(utilisateur):
        return RedirectResponse("/dashboard", status_code=303)

    lignes = session.exec(
        select(DemandeAccompagnement, Utilisateur)
        .join(Utilisateur, Utilisateur.id == DemandeAccompagnement.repetiteur_id)
        .where(DemandeAccompagnement.etudiant_id == utilisateur.id)
        .order_by(DemandeAccompagnement.date_creation.desc())
        .limit(50)
    ).all()
    demandes = [
        {
            "matiere": demande.matiere,
            "niveau": demande.niveau,
            "message": demande.message,
            "statut": demande.statut,
            "date_creation": demande.date_creation,
            "repetiteur_nom": nom_public_repetiteur(repetiteur.nom),
            "profil_disponible": _est_repetiteur_verifie(repetiteur),
        }
        for demande, repetiteur in lignes
    ]
    return templates.TemplateResponse(
        request,
        "mes_demandes_repetiteur.html",
        {"utilisateur": utilisateur, "demandes": demandes},
    )


@router.post("/repetiteur/demandes/{demande_id}/traiter")
def traiter_demande_accompagnement(
    request: Request,
    demande_id: int,
    action: str = Form(""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Un répétiteur ne peut répondre qu'aux demandes qui lui sont adressées."""
    repetiteur = utilisateur_courant(request, session)
    if not repetiteur:
        return RedirectResponse("/connexion", status_code=303)
    if not _est_repetiteur_verifie(repetiteur):
        return RedirectResponse("/dashboard", status_code=303)

    demande = session.get(DemandeAccompagnement, demande_id)
    if (
        not demande
        or demande.repetiteur_id != repetiteur.id
        or demande.statut != STATUT_EN_ATTENTE
        or action not in {STATUT_ACCEPTEE, STATUT_REFUSEE}
    ):
        return RedirectResponse("/dashboard?erreur=demande_indisponible#rep-demandes", status_code=303)

    demande.statut = action
    demande.date_traitement = datetime.utcnow()
    session.add(demande)
    session.commit()
    return RedirectResponse(
        f"/dashboard?ok=demande_{action}#rep-demandes",
        status_code=303,
    )
