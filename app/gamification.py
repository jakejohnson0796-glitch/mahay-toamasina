"""XP, missions quotidiennes et badges de Gasy Mahay."""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from .models import ActionGamification, Utilisateur


POINTS_ACTION = {
    "tuteur": 15,
    "quiz": 25,
    "cercle": 20,
    "document": 40,
    "cercle_rejoint": 10,
}

MISSIONS = [
    {
        "id": "tuteur",
        "titre": "Poser une question au Tuteur IA",
        "description": "Demande une explication sur une notion qui te bloque.",
        "points": POINTS_ACTION["tuteur"],
        "action": "tuteur",
        "lien": "/tuteur",
        "bouton": "Demander",
    },
    {
        "id": "quiz",
        "titre": "Terminer un quiz",
        "description": "Fais un quiz pour tester ce que tu sais déjà.",
        "points": POINTS_ACTION["quiz"],
        "action": "quiz",
        "lien": "/quiz",
        "bouton": "Faire un quiz",
    },
    {
        "id": "cercle",
        "titre": "Participer à un cercle",
        "description": "Écris un message utile à ton groupe d'étude.",
        "points": POINTS_ACTION["cercle"],
        "action": "cercle",
        "lien": "/cercles",
        "bouton": "Ouvrir les cercles",
    },
    {
        "id": "document",
        "titre": "Partager une ressource",
        "description": "Dépose un document que tu as le droit de diffuser.",
        "points": POINTS_ACTION["document"],
        "action": "document",
        "lien": "/documents/upload",
        "bouton": "Partager",
    },
]

BADGES = [
    {
        "id": "premier_pas",
        "nom": "Premier pas",
        "icone": "🌱",
        "description": "Effectuer ta première action d'apprentissage.",
        "objectif": 1,
        "type": "total",
    },
    {
        "id": "curieux",
        "nom": "Curieux",
        "icone": "🧠",
        "description": "Effectuer 5 actions d'apprentissage.",
        "objectif": 5,
        "type": "total",
    },
    {
        "id": "contributeur",
        "nom": "Contributeur",
        "icone": "📚",
        "description": "Partager 1 ressource.",
        "objectif": 1,
        "type": "action",
        "action": "document",
    },
    {
        "id": "mentor",
        "nom": "Mentor",
        "icone": "💬",
        "description": "Participer 5 fois dans les cercles.",
        "objectif": 5,
        "type": "action",
        "action": "cercle",
    },
    {
        "id": "regulier",
        "nom": "Régulier",
        "icone": "🔥",
        "description": "Étudier au moins 3 jours consécutifs.",
        "objectif": 3,
        "type": "streak",
    },
    {
        "id": "ambassadeur",
        "nom": "Ambassadeur",
        "icone": "🎓",
        "description": "Effectuer 20 actions et partager 5 ressources.",
        "objectif": 20,
        "type": "ambassadeur",
    },
]


def enregistrer_action(
    session: Session,
    utilisateur_id: int,
    action: str,
    *,
    source_type: str = "",
    source_key: str = "",
) -> Optional[ActionGamification]:
    """Ajoute une récompense XP une seule fois pour une source donnée."""
    points = POINTS_ACTION.get(action)
    if points is None:
        raise ValueError(f"Action de gamification inconnue: {action}")

    existante = session.exec(
        select(ActionGamification)
        .where(ActionGamification.utilisateur_id == utilisateur_id)
        .where(ActionGamification.action == action)
        .where(ActionGamification.source_type == source_type)
        .where(ActionGamification.source_key == source_key)
        .limit(1)
    ).first()
    if existante:
        return existante

    evenement = ActionGamification(
        utilisateur_id=utilisateur_id,
        action=action,
        source_type=source_type,
        source_key=source_key,
        points=points,
    )
    session.add(evenement)
    return evenement


def _evenements(session: Session, utilisateur_id: int):
    return session.exec(
        select(ActionGamification)
        .where(ActionGamification.utilisateur_id == utilisateur_id)
        .order_by(ActionGamification.date_creation.desc())
    ).all()


def jours_actifs_consecutifs(session: Session, utilisateur_id: int) -> int:
    dates = {
        evenement.date_creation.date()
        for evenement in _evenements(session, utilisateur_id)
    }
    if not dates:
        return 0

    jour = datetime.utcnow().date()
    if jour not in dates:
        jour = max(dates)

    total = 0
    while jour in dates:
        total += 1
        jour -= timedelta(days=1)
    return total


def resume(session: Session, utilisateur: Utilisateur) -> dict:
    evenements = _evenements(session, utilisateur.id)
    total_xp = sum(e.points for e in evenements)

    aujourd_hui = datetime.utcnow().date()
    actions_du_jour = {
        e.action
        for e in evenements
        if e.date_creation.date() == aujourd_hui
    }

    missions = []
    for mission in MISSIONS:
        missions.append(
            {
                **mission,
                "terminee": mission["action"] in actions_du_jour,
            }
        )

    mission_completee = all(m["terminee"] for m in missions)
    bonus_mission = 0
    if mission_completee:
        bonus_mission = 25
        # Le bonus journalier est lui aussi idempotent.
        bonus = session.exec(
            select(ActionGamification)
            .where(ActionGamification.utilisateur_id == utilisateur.id)
            .where(ActionGamification.action == "bonus_mission")
            .where(ActionGamification.source_type == "jour")
            .where(ActionGamification.source_key == aujourd_hui.isoformat())
            .limit(1)
        ).first()
        if not bonus:
            bonus = ActionGamification(
                utilisateur_id=utilisateur.id,
                action="bonus_mission",
                source_type="jour",
                source_key=aujourd_hui.isoformat(),
                points=bonus_mission,
            )
            session.add(bonus)
            session.commit()
            evenements.append(bonus)
            total_xp += bonus_mission

    actions_total = len(evenements)
    compte_actions = {}
    for evenement in evenements:
        compte_actions[evenement.action] = compte_actions.get(evenement.action, 0) + 1

    jours = jours_actifs_consecutifs(session, utilisateur.id)
    badges = []
    for badge in BADGES:
        if badge["type"] == "total":
            progression = actions_total
        elif badge["type"] == "action":
            progression = compte_actions.get(badge["action"], 0)
        elif badge["type"] == "streak":
            progression = jours
        else:
            progression = min(actions_total, compte_actions.get("document", 0))
        progression_clamp = min(progression, badge["objectif"])
        badges.append(
            {
                **badge,
                "progression": progression_clamp,
                "pourcentage": round(progression_clamp * 100 / badge["objectif"]),
                "obtenu": progression >= badge["objectif"],
            }
        )

    niveau = 1 + total_xp // 250
    xp_dans_niveau = total_xp % 250
    xp_prochain = 250

    return {
        "total_xp": total_xp,
        "niveau": niveau,
        "xp_dans_niveau": xp_dans_niveau,
        "xp_prochain": xp_prochain,
        "streak": jours,
        "missions": missions,
        "mission_completee": mission_completee,
        "bonus_mission": bonus_mission,
        "badges": badges,
        "actions_total": actions_total,
        "compte_actions": compte_actions,
    }


def classement(session: Session, utilisateur: Utilisateur, limit: int = 8) -> dict:
    """Classement de la même promotion si le profil le permet, sinon global."""
    requete = (
        select(
            Utilisateur.id,
            Utilisateur.nom,
            Utilisateur.filiere_id,
            Utilisateur.niveau,
            func.coalesce(func.sum(ActionGamification.points), 0).label("xp"),
        )
        .outerjoin(
            ActionGamification,
            ActionGamification.utilisateur_id == Utilisateur.id,
        )
        .where(Utilisateur.banni == False)  # noqa: E712
    )

    contexte = "global"
    if utilisateur.filiere_id and utilisateur.niveau:
        requete = requete.where(
            Utilisateur.filiere_id == utilisateur.filiere_id,
            Utilisateur.niveau == utilisateur.niveau,
        )
        contexte = "ta promotion"

    lignes = session.exec(
        requete.group_by(
            Utilisateur.id,
            Utilisateur.nom,
            Utilisateur.filiere_id,
            Utilisateur.niveau,
        )
        .order_by(func.coalesce(func.sum(ActionGamification.points), 0).desc(), Utilisateur.id.asc())
    ).all()

    classement = []
    rang_utilisateur = None
    xp_utilisateur = 0
    for rang, ligne in enumerate(lignes, start=1):
        item = {
            "rang": rang,
            "utilisateur_id": ligne[0],
            "nom": ligne[1],
            "xp": int(ligne[4] or 0),
        }
        classement.append(item)
        if ligne[0] == utilisateur.id:
            rang_utilisateur = rang
            xp_utilisateur = int(ligne[4] or 0)

    return {
        "contexte": contexte,
        "top": classement[:limit],
        "rang": rang_utilisateur or (len(classement) + 1),
        "xp_utilisateur": xp_utilisateur,
    }


def donnees_defis(session: Session, utilisateur: Utilisateur) -> dict:
    return {
        "gamification": resume(session, utilisateur),
        "classement": classement(session, utilisateur),
    }
