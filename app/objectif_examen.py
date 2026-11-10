"""Règles sûres et explicites pour les premiers parcours Objectif Examen.

Les quiz générés sont des entraînements non officiels. Les programmes et options
sont choisis explicitement par l'apprenant ; aucune annale n'est présentée comme
un sujet officiel ni aucun barème n'est inventé.
"""
from __future__ import annotations


def construire_contexte_examen(
    objectif: str,
    *,
    option_ps: str | None = None,
    serie: str | None = None,
) -> dict[str, str]:
    """Valide le parcours choisi et prépare une consigne courte pour le quiz IA."""
    code = str(objectif or "").strip().lower()

    if code == "bepc_ps":
        option = str(option_ps or "").strip().upper()
        if option not in {"A", "B"}:
            raise ValueError("Pour le BEPC ancien programme, choisis l'option A ou B.")
        label = f"BEPC 2027 · Programme scolaire (PS) · Option {option}"
        instruction = (
            f"BEPC Madagascar 2027, ancien Programme scolaire (PS), option {option}"
        )
        return {"code": code, "label": label, "instruction": instruction}

    if code == "bepc_pe":
        label = "BEPC 2027 · Nouveau programme d'études (PE)"
        instruction = "BEPC Madagascar 2027, nouveau Programme d'études (PE)"
        return {"code": code, "label": label, "instruction": instruction}

    if code == "cepe":
        label = "CEPE · Classe T5"
        instruction = (
            "CEPE Madagascar, niveau primaire T5. Prépare un entraînement pédagogique "
            "non officiel portant uniquement sur la matière choisie et les apprentissages "
            "du référentiel MEN RAPE T5 validé. Ne prétends jamais reproduire un sujet officiel."
        )
        return {"code": code, "label": label, "instruction": instruction}

    if code == "baccalaureat":
        serie_validee = str(serie or "").strip()
        if not serie_validee or len(serie_validee) > 60:
            raise ValueError("La série du Baccalauréat doit être renseignée dans ton profil vérifié.")
        label = f"Baccalauréat · {serie_validee}"
        instruction = f"Baccalauréat Madagascar, série {serie_validee}"
        return {"code": code, "label": label, "instruction": instruction}

    raise ValueError("Cet objectif d'examen n'est pas disponible.")
