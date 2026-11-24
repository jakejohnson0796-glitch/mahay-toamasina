"""Gestion centralisée de la langue choisie pour l'interface et les contenus IA."""

from __future__ import annotations

from typing import Any

LANGUES_AUTORISEES = frozenset({"fr", "mg", "en"})

_INSTRUCTIONS_SORTIE = {
    "fr": (
        "LANGUE DE SORTIE OBLIGATOIRE : français. Rédige tout le texte destiné à "
        "l'apprenant en français naturel et correct : questions, choix, explications, "
        "notions, indices, exemples, exercices, corrections et retours. Ne mélange "
        "pas le français avec l'anglais ou le malagasy. Conserve sans les traduire "
        "les noms propres, identifiants, extraits cités nécessaires, termes techniques "
        "officiels et code."
    ),
    "mg": (
        "Fiteny tsy maintsy ampiasaina : MALAGASY. Soraty amin'ny teny malagasy "
        "mazava sy voajanahary ny lahatsoratra rehetra ho hitan'ny mpianatra : "
        "fanontaniana, safidy, fanazavana, lohahevitra, toromarika, ohatra, fanazaran-tena, "
        "valiny ary fanamarihana. Aza afangaro amin'ny teny frantsay na anglisy. "
        "Avelao tsy adika ny anarana manokana, kaody, marika ara-tsiansa, teny teknika "
        "ofisialy ary sombin-dahatsoratra tsy maintsy tazonina."
    ),
    "en": (
        "MANDATORY OUTPUT LANGUAGE: English. Write all learner-facing text in clear, "
        "natural English: questions, answer choices, explanations, topic labels, hints, "
        "examples, exercises, corrections and feedback. Do not mix English with French "
        "or Malagasy. Keep proper names, identifiers, official technical terms, quoted "
        "source excerpts when necessary, and code unchanged."
    ),
}


def normaliser_langue(langue: Any) -> str:
    """N'accepte que les trois langues proposées par MITARIDALA."""
    valeur = str(langue or "").strip().lower()
    return valeur if valeur in LANGUES_AUTORISEES else "fr"


def langue_depuis_requete(request: Any) -> str:
    """Lit la préférence synchronisée par le navigateur via le cookie mahay-langue."""
    cookies = getattr(request, "cookies", None) or {}
    return normaliser_langue(cookies.get("mahay-langue"))


def instruction_langue_sortie(langue: Any = "fr") -> str:
    """Instruction unique réutilisée par les générateurs, correcteurs et arbitres IA."""
    return _INSTRUCTIONS_SORTIE[normaliser_langue(langue)]
