"""Répertoire de ressources externes pour la préparation aux examens.

Les liens renvoient vers les éditeurs d'origine. MITARIDALA ne copie pas ces
documents et ne présente pas les contenus de tiers comme vérifiés ou officiels.
"""
from __future__ import annotations

from typing import Any


_RESSOURCES: tuple[dict[str, Any], ...] = (
    {
        "id": "men-rape-t5-cepe",
        "nom": "Ministère de l’Éducation nationale — RAPE T5",
        "examens": ("cepe",),
        "type_contenu": "Référentiel officiel et répartition annuelle T5",
        "description": (
            "Document du MEN pour la dernière classe du primaire. Il sert de repère "
            "pédagogique pour les entraînements CEPE ; il ne s’agit pas d’une banque d’annales."
        ),
        "url": "https://plateforme.education.mg/bibliotheque-numerique/theme/biblio/pix/pdf/RAPE_T5.pdf",
        "url_label": "Consulter le RAPE T5",
        "limites": (
            "Le RAPE organise les apprentissages annuels et ne remplace pas le "
            "Programme d’Études complet ni les consignes officielles de la session CEPE."
        ),
        "source_note": "Source : bibliothèque numérique du Ministère de l’Éducation nationale.",
    },
    {
        "id": "laza-adina",
        "nom": "Laza-Adina",
        "examens": ("bepc", "baccalaureat"),
        "type_contenu": "Annales, sujets corrigés, fiches et exercices",
        "description": (
            "La plateforme présente des sujets et fiches pour la classe de 3e, "
            "ainsi que des sujets corrigés pour plusieurs séries du Baccalauréat."
        ),
        "url": "https://laza-adina.com/a-propos/",
        "url_label": "Consulter la présentation",
        "limites": (
            "MITARIDALA ne vérifie pas chaque document. Pour le BEPC 2027, "
            "contrôle impérativement la correspondance avec le PS ou le PE et, "
            "pour le PS, avec l'option A ou B."
        ),
        "source_note": "Informations publiées par la plateforme.",
    },
    {
        "id": "madagasy-exams",
        "nom": "Madagasy Exams",
        "examens": ("baccalaureat",),
        "type_contenu": "Annales du Baccalauréat et corrigés annoncés par l'éditeur",
        "description": (
            "L'application présente des épreuves du BAC classées par série, "
            "matière et année, avec lecture hors connexion."
        ),
        "url": "https://yousef-labs.com/madagasy-exams",
        "url_label": "Consulter la présentation",
        "limites": (
            "La page d'assistance précise que certains sujets n'ont pas de corrigé. "
            "MITARIDALA ne vérifie pas individuellement les fichiers ni leurs corrigés."
        ),
        "source_note": (
            "L'éditeur indique que les épreuves et corrigés proviennent de la "
            "médiathèque AccèsMad."
        ),
    },
)


def ressources_pour_cycle(cycle: str | None) -> list[dict[str, Any]]:
    """Retourne les ressources correspondant au cycle, sans les déclarer validées."""
    cycle_normalise = str(cycle or "").strip().casefold()
    if cycle_normalise == "primaire":
        examens_cibles = {"cepe"}
    elif cycle_normalise == "college":
        examens_cibles = {"bepc"}
    elif cycle_normalise == "lycee":
        examens_cibles = {"baccalaureat"}
    else:
        examens_cibles = {"bepc", "baccalaureat"}

    return [
        {**ressource, "examens_affiches": tuple(
            examen for examen in ressource["examens"] if examen in examens_cibles
        )}
        for ressource in _RESSOURCES
        if examens_cibles.intersection(ressource["examens"])
    ]
