"""Mission d'apprentissage guidée à partir de la carte de connaissances.

Le moteur ne crée aucune nouvelle donnée. Il transforme la priorité déjà
calculée par knowledge_map en une courte séquence d'actions cohérente :
une notion, un objectif, puis une preuve.
"""
from typing import Iterable, Optional

from .models import ProgressionNotion


def _score(progression: ProgressionNotion) -> int:
    return max(0, min(100, int(progression.score_maitrise or 0)))


def _revision_due(progression: ProgressionNotion) -> bool:
    return bool(progression.prochaine_revision_le and progression.prochaine_revision_le <= __import__("datetime").datetime.utcnow())


def construire_mission(carte: dict, progressions: Iterable[ProgressionNotion]) -> dict:
    """Construit une mission courte et explicable pour une seule notion."""
    cible = carte.get("prochaine")
    if not cible:
        return {
            "active": False,
            "notion": None,
            "matiere": None,
            "progression_id": None,
            "score": None,
            "titre": "Aucune priorité critique pour l'instant",
            "objectif": "Choisis une nouvelle notion et commence par un quiz pour créer les premières preuves.",
            "duree": "10–15 min",
            "action_principale": None,
            "action_secondaire": "quiz",
            "etapes": [],
            "message": "La mission guidée apparaîtra dès que le moteur aura assez de données pour identifier une priorité.",
        }

    progression = next(
        (
            item for item in progressions
            if int(item.id or 0) == int(cible.get("id") or 0)
        ),
        None,
    )
    if progression is None:
        return {
            "active": False,
            "notion": cible.get("notion"),
            "matiere": cible.get("matiere"),
            "progression_id": cible.get("id"),
            "score": cible.get("score"),
            "titre": "Priorité détectée",
            "objectif": "Ouvre la carte pour comprendre les relations avant de choisir ton prochain exercice.",
            "duree": "10–15 min",
            "action_principale": None,
            "action_secondaire": "carte",
            "etapes": [],
            "message": "La priorité existe dans la carte mais son détail de progression n'est plus disponible.",
        }

    score = _score(progression)
    erreurs = int(progression.nb_erreurs or 0)
    due = _revision_due(progression)

    if score < 50 or erreurs >= 2:
        titre = "Débloquer une faiblesse"
        objectif = "Comprendre l'erreur principale, puis réussir 5 questions ciblées sans refaire mécaniquement la même erreur."
        action = "tuteur"
        action_label = "Commencer avec le Tuteur IA"
        message = "Ton historique montre une fragilité réelle : on commence par comprendre avant de re-tester."
    elif score < 75 or due:
        titre = "Stabiliser la notion"
        objectif = "Réussir un entraînement ciblé et transformer une réussite ponctuelle en compétence régulière."
        action = "quiz"
        action_label = "Lancer le quiz ciblé"
        message = "Tu es en cours d'acquisition : le meilleur levier maintenant est une pratique courte et ciblée."
    else:
        titre = "Prouver la maîtrise"
        objectif = "Obtenir une nouvelle preuve de maîtrise sur cette notion plutôt que se fier au seul score."
        action = "quiz"
        action_label = "Passer l'épreuve de preuve"
        message = "Le score est bon. La prochaine étape est de vérifier que la réussite tient sur une nouvelle série."

    etapes = [
        {
            "numero": "01",
            "titre": "Comprendre",
            "texte": "Identifier la règle, la méthode et l'erreur à éviter.",
            "type": "tuteur" if action == "tuteur" else "rappel",
            "etat": "prioritaire",
        },
        {
            "numero": "02",
            "titre": "Pratiquer",
            "texte": "Faire 5 questions ciblées sur exactement la même notion.",
            "type": "quiz",
            "etat": "a_faire",
        },
        {
            "numero": "03",
            "titre": "Vérifier",
            "texte": "Comparer la nouvelle preuve avec ton historique et décider de la suite.",
            "type": "preuve",
            "etat": "a_faire",
        },
    ]

    return {
        "active": True,
        "notion": progression.notion,
        "matiere": progression.matiere,
        "progression_id": progression.id,
        "score": score,
        "erreurs": erreurs,
        "revision_due": due,
        "titre": titre,
        "objectif": objectif,
        "duree": "12–15 min",
        "action_principale": action,
        "action_label": action_label,
        "action_secondaire": "quiz" if action == "tuteur" else "tuteur",
        "message": message,
        "etapes": etapes,
        "preuve": "Nouvelle preuve attendue après l'entraînement ciblé.",
    }
