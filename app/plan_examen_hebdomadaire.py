"""Construction déterministe d'un programme de révision sur sept jours.

Le planning s'appuie uniquement sur les notions déjà évaluées du niveau courant.
Il ne prétend pas connaître la date officielle de l'examen et ne crée pas de
progression artificielle lorsque l'élève n'a pas encore de résultats.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Any


_JOURS = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche")


def construire_plan_hebdomadaire(
    progressions: Iterable[Any],
    *,
    maintenant: datetime | None = None,
    limite_notions: int = 14,
) -> list[dict]:
    """Répartit jusqu'à deux notions prioritaires par jour sur les sept jours."""
    instant = maintenant or datetime.utcnow()
    aujourd_hui = instant.date()
    limite = max(1, min(int(limite_notions or 14), 14))

    candidates = []
    vus = set()
    for progression in progressions or []:
        if int(getattr(progression, "nb_questions", 0) or 0) <= 0:
            continue
        matiere = str(getattr(progression, "matiere", "") or "").strip()
        notion = str(getattr(progression, "notion", "") or "").strip()
        identifiant = getattr(progression, "id", None)
        cle = (matiere.casefold(), notion.casefold(), identifiant)
        if not matiere or not notion or cle in vus:
            continue
        vus.add(cle)
        prochaine = getattr(progression, "prochaine_revision_le", None)
        due = bool(prochaine and prochaine <= instant)
        try:
            score = max(0, min(100, int(getattr(progression, "score_maitrise", 0) or 0)))
        except (TypeError, ValueError):
            score = 0
        candidates.append({
            "matiere": matiere,
            "notion": notion,
            "score": score,
            "nb_erreurs": max(0, int(getattr(progression, "nb_erreurs", 0) or 0)),
            "revision_due": due,
            "progression_id": identifiant,
        })

    candidates.sort(key=lambda item: (
        not item["revision_due"], item["score"], -item["nb_erreurs"],
        item["matiere"].casefold(), item["notion"].casefold(),
    ))
    candidates = candidates[:limite]

    jours = []
    for index, nom in enumerate(_JOURS):
        date_jour = aujourd_hui + timedelta(days=index)
        taches = candidates[index * 2:(index + 1) * 2]
        jours.append({
            "index": index + 1,
            "nom": nom,
            "date": date_jour.strftime("%d/%m"),
            "date_iso": date_jour.isoformat(),
            "taches": taches,
            "duree_minutes": len(taches) * 20,
        })
    return jours
