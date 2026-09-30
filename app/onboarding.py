"""Parcours d'activation et des 7 premiers jours."""
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from .models import ActionGamification, Utilisateur


PREMIERES_ETAPES = [
    {
        "id": "tuteur",
        "titre": "Poser ta première question au Tuteur IA",
        "description": "Demande une explication sur une notion qui te bloque.",
        "lien": "/tuteur",
        "bouton": "Poser ma question",
        "action": "tuteur",
    },
    {
        "id": "quiz",
        "titre": "Terminer ton premier quiz",
        "description": "Teste tes connaissances avec quelques questions.",
        "lien": "/quiz",
        "bouton": "Faire mon quiz",
        "action": "quiz",
    },
    {
        "id": "cercle",
        "titre": "Rejoindre ton premier cercle",
        "description": "Trouve les étudiants de ta filière et de ton niveau.",
        "lien": "/cercles",
        "bouton": "Trouver un cercle",
        "action": "cercle_rejoint",
    },
]

SEMAINE = [
    {
        "jour": 1,
        "titre": "Découvrir le Tuteur IA",
        "description": "Pose une vraie question de cours et garde la réponse dans ton espace.",
        "action": "tuteur",
        "lien": "/tuteur",
        "label": "Poser une question",
        "points": 15,
    },
    {
        "jour": 2,
        "titre": "Tester tes connaissances",
        "description": "Termine un quiz et regarde les notions à revoir.",
        "action": "quiz",
        "lien": "/quiz",
        "label": "Faire un quiz",
        "points": 25,
    },
    {
        "jour": 3,
        "titre": "Rejoindre la communauté",
        "description": "Rejoins le cercle correspondant à ton parcours.",
        "action": "cercle_rejoint",
        "lien": "/cercles",
        "label": "Trouver un cercle",
        "points": 10,
    },
    {
        "jour": 4,
        "titre": "Partager une ressource",
        "description": "Aide d'autres étudiants avec un document que tu as le droit de diffuser.",
        "action": "document",
        "lien": "/documents/upload",
        "label": "Partager",
        "points": 40,
    },
    {
        "jour": 5,
        "titre": "Participer dans un cercle",
        "description": "Pose une question, aide un camarade ou partage une méthode.",
        "action": "cercle",
        "lien": "/cercles",
        "label": "Participer",
        "points": 20,
    },
    {
        "jour": 6,
        "titre": "Reprendre une notion faible",
        "description": "Consulte ton parcours personnalisé et révise une notion prioritaire.",
        "action": "revision",
        "lien": "/mes-revisions",
        "label": "Mes révisions",
        "points": 10,
    },
    {
        "jour": 7,
        "titre": "Faire ton bilan de la semaine",
        "description": "Refais un quiz ou une question Tuteur et regarde ton évolution.",
        "action": "quiz",
        "lien": "/quiz",
        "label": "Faire le bilan",
        "points": 25,
    },
]


def _actions(session: Session, utilisateur_id: int, depuis: Optional[datetime] = None):
    requete = select(ActionGamification).where(
        ActionGamification.utilisateur_id == utilisateur_id
    )
    if depuis is not None:
        requete = requete.where(ActionGamification.date_creation >= depuis)
    return session.exec(
        requete.order_by(ActionGamification.date_creation.asc())
    ).all()


def est_termine(session: Session, utilisateur: Utilisateur) -> bool:
    if utilisateur.onboarding_termine_le:
        return True

    actions = _actions(session, utilisateur.id)
    actions_requises = {"tuteur", "quiz", "cercle_rejoint"}
    termine = actions_requises.issubset({a.action for a in actions})
    if termine:
        utilisateur.onboarding_termine_le = datetime.utcnow()
        session.add(utilisateur)
        session.commit()
    return termine


def assurer_demarrage(session: Session, utilisateur: Utilisateur) -> datetime:
    if utilisateur.onboarding_commence_le is None:
        utilisateur.onboarding_commence_le = datetime.utcnow()
        session.add(utilisateur)
        session.commit()
        session.refresh(utilisateur)
    return utilisateur.onboarding_commence_le


def donnees_onboarding(session: Session, utilisateur: Utilisateur) -> dict:
    debut = assurer_demarrage(session, utilisateur)
    actions = _actions(session, utilisateur.id, debut)
    actions_noms = {a.action for a in actions}

    etapes = []
    for etape in PREMIERES_ETAPES:
        terminee = etape["action"] in actions_noms
        etapes.append({**etape, "terminee": terminee})

    onboarding_termine = est_termine(session, utilisateur)
    jour_calcule = max(1, (datetime.utcnow().date() - debut.date()).days + 1)
    jour = min(jour_calcule, 7)

    plan = []
    for item in SEMAINE:
        terminee = item["action"] in actions_noms
        plan.append(
            {
                **item,
                "terminee": terminee,
                "actif": item["jour"] == jour,
                "accessible": item["jour"] <= jour,
            }
        )

    return {
        "onboarding_termine": onboarding_termine,
        "debut": debut,
        "jour": jour,
        "etapes": etapes,
        "etapes_terminees": sum(1 for e in etapes if e["terminee"]),
        "plan_7_jours": plan,
    }
