"""Transport texte brut des contenus IA.

Le modèle peut produire du LaTeX, du Markdown ou des marqueurs historiques.
Ce module ne doit PLUS transformer le contenu pédagogique : la mise en forme
est réalisée exclusivement par app/static/js/rendu_ia.js dans le navigateur.

La fonction convertir_math_transport_texte est conservée pour compatibilité
avec les anciens imports/tests, mais elle est désormais volontairement
identitaire.
"""

from __future__ import annotations

from typing import Any, Mapping

MARKER_INLINE = "[[MATH]]"
MARKER_INLINE_END = "[[/MATH]]"
MARKER_DISPLAY = "[[DISPLAY]]"
MARKER_DISPLAY_END = "[[/DISPLAY]]"
MARKER_CHEM = "[[CHEM]]"
MARKER_CHEM_END = "[[/CHEM]]"

REGLES_FORMAT = r"""
CONTRAT DE FORMATAGE UNIQUE DU TUTEUR IA ET DU QUIZ IA — OBLIGATOIRE :

- Réponds en français et en Markdown clair et pédagogique.
- Le code informatique reste dans des blocs Markdown clôturés.
- Les tableaux Markdown servent aux données tabulaires, jamais à représenter une matrice.
- MATHS/PHYSIQUE : utilise le vrai LaTeX avec délimiteurs :
  inline : \( ... \)
  bloc : \[ ... \]
  et les commandes \frac{}, \sqrt{}, \sum, \int, \begin{aligned}, \begin{pmatrix},
  \begin{cases}, \mathrm{}, \vec{}, \nabla, \le, \ge, \neq, \times, \cdot, etc.
- CHIMIE : utilise mhchem uniquement dans un délimiteur mathématique :
  \( \ce{H2O} \)
  \( \ce{2H2 + O2 -> 2H2O} \)
  \( \ce{Fe^{3+}} \)
  Ne produis jamais \ce{...} nu hors délimiteur.
- Ne remplace jamais le vrai LaTeX par sqrt(...), sum(...), int(...), <= ou >=
  lorsqu'une expression doit être rendue comme une formule.
- Ne modifie pas les antislashs, accolades ou doubles antislashs d'un LaTeX valide.
  En particulier, les \\ entre lignes d'un environnement aligned/matrix doivent rester \\.
- La sortie est transportée dans un tool-call JSON strict : le JSON doit être valide.
  Les antislashs du contenu doivent donc être échappés selon JSON afin qu'après
  json.loads() la chaîne métier contienne le vrai LaTeX.
- Conserve fidèlement les sauts de ligne, tabulations et retours chariot.
- N'utilise pas les anciens marqueurs [[MATH]], [[DISPLAY]] ou [[CHEM]].
- Vérifie calculs, signes, unités, dimensions, indices et résultats.
- Pour un QCM, une seule réponse doit être correcte et les choix ne contiennent
  aucun préfixe A/B/C/D/E.
"""

PROMPT_TRANSPORT_SANS_ANTISLASH = REGLES_FORMAT


def convertir_math_transport_texte(valeur: Any) -> str:
    """Retourne le texte exactement tel qu'il a été reçu.

    Important : aucune conversion de LaTeX, de Markdown, de chimie ou
    d'encodage n'est effectuée ici. Cela évite les doubles transformations
    et les divergences entre le Quiz IA et le Tuteur IA.
    """
    return "" if valeur is None else str(valeur)


def normaliser_structure_quiz(questions: list[Mapping[str, Any]] | None) -> list[dict]:
    """Copie la structure du quiz sans toucher aux champs pédagogiques."""
    resultat: list[dict] = []
    for question in questions or []:
        item = dict(question)
        item["question"] = convertir_math_transport_texte(item.get("question", ""))
        item["choix"] = [
            convertir_math_transport_texte(choix)
            for choix in (item.get("choix") or [])
        ]
        item["explication"] = convertir_math_transport_texte(
            item.get("explication", "")
        )
        resultat.append(item)
    return resultat


def normaliser_structure_tuteur(
    reponse: Mapping[str, Any] | None,
) -> dict[str, str]:
    """Copie les quatre sections du Tuteur sans transformation de contenu."""
    source = reponse or {}
    return {
        "explication": convertir_math_transport_texte(source.get("explication", "")),
        "exemple": convertir_math_transport_texte(source.get("exemple", "")),
        "exercice": convertir_math_transport_texte(source.get("exercice", "")),
        "correction": convertir_math_transport_texte(source.get("correction", "")),
    }
