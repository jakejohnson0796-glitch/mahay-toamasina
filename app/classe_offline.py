"""Construction de packs de cours lisibles hors connexion.

Les packs ne contiennent que le contenu pédagogique partagé du cours :
aucune note individuelle, copie, présence, jeton ou donnée personnelle.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

MAX_SEANCES_HORS_LIGNE = 100
MAX_DEVOIRS_HORS_LIGNE = 100
MAX_TEXTE_HORS_LIGNE = 5000


def _texte(valeur: Any, maximum: int = MAX_TEXTE_HORS_LIGNE) -> str:
    return str(valeur or "").strip()[:maximum]


def _date_iso(valeur: Any) -> str | None:
    return valeur.isoformat() if isinstance(valeur, datetime) else None


def _valeur_enum(valeur: Any) -> str:
    return str(getattr(valeur, "value", valeur or ""))


def construire_pack_hors_ligne(cours: Any, seances: list[Any], devoirs: list[Any]) -> dict:
    """Retourne une structure versionnée, bornée et sans données individuelles."""
    toutes_seances = list(seances or [])
    tous_devoirs = list(devoirs or [])
    selection_seances = toutes_seances[:MAX_SEANCES_HORS_LIGNE]
    selection_devoirs = tous_devoirs[:MAX_DEVOIRS_HORS_LIGNE]
    return {
        "schema_version": 1,
        "genere_le": datetime.utcnow().isoformat() + "Z",
        "cours": {
            "id": int(cours.id),
            "nom": _texte(cours.nom, 240),
            "matiere": _texte(cours.matiere, 160),
            "niveau": _texte(cours.niveau, 100),
            "description": _texte(cours.description, 3000),
            "objectifs": _texte(cours.objectifs, 3000),
        },
        "seances": [
            {
                "id": int(item.id),
                "titre": _texte(item.titre, 240),
                "description": _texte(item.description),
                "statut": _valeur_enum(item.statut),
                "cree_le": _date_iso(item.date_creation),
            }
            for item in selection_seances
        ],
        "devoirs": [
            {
                "id": int(item.id),
                "titre": _texte(item.titre, 240),
                "description": _texte(item.description),
                "date_limite": _date_iso(item.date_limite),
                "bareme": float(item.bareme or 0),
                "coefficient": float(item.coefficient or 1),
                "periode": _texte(item.periode, 80),
                "clos": bool(item.est_clos),
            }
            for item in selection_devoirs
        ],
        "limites": {
            "seances_tronquees": len(toutes_seances) > len(selection_seances),
            "devoirs_tronques": len(tous_devoirs) > len(selection_devoirs),
        },
    }
