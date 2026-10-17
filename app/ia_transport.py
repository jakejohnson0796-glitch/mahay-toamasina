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
- OBLIGATOIRE : chaque équation, puissance, fraction, intégrale ou variable avec indice
  doit être entièrement placée entre \( ... \) ou \[ ... \], même au milieu d'une phrase.
  Exemples : « \(f(x)=3x^{2}+2x-5\) » et
  « \(\displaystyle\int_{0}^{2}(x+1)\,dx\) ».
- FORMULES COMPOSÉES : encadre toute l'expression, et pas seulement l'opérateur.
  Exemples exacts : « \(7\times 8+9=65\) » et « \(\sqrt{1000}\approx31{,}6\) ».
  N'écris jamais « sqrt{1000}approx31,6 » sans commandes LaTeX ni délimiteurs.
- PHYSIQUE : conserve symboles, indices, puissances et unités dans l'expression :
  « \(\Delta E=\hbar\omega\) », « \(v=3\,\mathrm{m/s}\) »,
  « \(a=2\,\mathrm{m/s^{2}}\) », « \(\rho=1\,\mathrm{kg/m^{3}}\) ».
  Les unités sont en \(\mathrm{...}\) et séparées de la valeur par \(\,\).
- RÉSULTATS : utilise la virgule décimale française à l'intérieur de la formule
  (ex. \(31{,}6\)) et vérifie les opérations avant d'expliquer l'estimation.
  Distingue explicitement la valeur exacte, l'approximation et l'arrondi; utilise ces trois
  termes lorsqu'ils sont pertinents. Pour un arrondi à la dizaine, explique le chiffre des
  unités et l'écart avec les deux dizaines voisines. Exemple : \(\sqrt{1000}\approx31{,}6\);
  à la dizaine la plus proche, \(31{,}6\) s'arrondit à \(30\), car il est plus proche de
  \(30\) que de \(40\). Ne présente jamais \(30\approx32\) comme une égalité d'estimation.
- CHIMIE : utilise mhchem uniquement dans un délimiteur mathématique :
  \( \ce{H2O} \)
  \( \ce{2H2 + O2 -> 2H2O} \)
  \( \ce{Fe^{3+}} \)
  Ne produis jamais \ce{...} nu hors délimiteur.
- Ne remplace jamais le vrai LaTeX par sqrt(...), sum(...), int(...), <= ou >=
  lorsqu'une expression doit être rendue comme une formule.
- Ne modifie pas les antislashs, accolades ou doubles antislashs d'un LaTeX valide.
  En particulier, les \\ entre lignes d'un environnement aligned/matrix doivent rester \\.
- Un symbole simple peut être écrit directement en Unicode (ex. ≤, ≥, √, π, ∑, ∫).
  Une fraction, une puissance, une intégrale avec bornes ou une formule composée doit
  être entièrement délimitée avec \( ... \) ou \[ ... \].
- La sortie est transportée dans un tool-call JSON strict : le JSON doit être valide.
  Dans la valeur JSON, une commande LaTeX doit être échappée comme du texte littéral
  (ex. \frac devient \\frac dans le JSON) ; ne laisse jamais le parseur transformer
  \f, \t, \n, \r ou \b en caractère de contrôle à l'intérieur d'une commande.
- Conserve fidèlement les sauts de ligne, tabulations et retours chariot.
- N'utilise pas les anciens marqueurs [[MATH]], [[DISPLAY]] ou [[CHEM]].
- CONTEXTE DES SYMBOLES : le sens d'un symbole dépend de la matière et du contexte. Ne remplace
  pas automatiquement un caractère Unicode, une commande LaTeX ou un opérateur de programmation.
- GREC : respecte la casse ; par exemple \\Delta et \\delta, \\Omega et \\omega ne sont pas interchangeables.
- CHIMIE : respecte exactement la casse des symboles d'éléments (Co n'est pas CO), les indices,
  les charges, les états (s), (l), (g), (aq), les coefficients et le sens des flèches de réaction.
- PHYSIQUE/SI : distingue les variables des unités ; conserve les exposants, indices, signes de produit
  (·), unités composées et dimensions. N'efface et ne convertis aucune unité.
- INFORMATIQUE : conserve exactement les opérateurs et les délimiteurs dans le code ; `<=`, `!=`,
  `===`, `&&`, `||`, `^`, `->`, `=>`, `?.` et `??` ont un sens dépendant du langage. Ne les réécris
  pas comme des comparaisons ou des formules mathématiques dans un bloc de code.
- COMPTABILITÉ : conserve la devise et les montants, notamment Ar et MGA ; ne transforme pas HT,
  TVA ou TTC en variables mathématiques.
- Ne fais aucune substitution globale sur `^`, `_`, `\\n`, les caractères de contrôle ou les symboles
  inconnus. Répare uniquement une séquence identifiée dans son contexte et couverte par un test.
- Ne confonds pas valeur exacte, approximation et arrondi : calcule d'abord, puis indique séparément l'approximation et l'arrondi demandé. Ne produis pas de contradictions telles que « arrondi à la dizaine = 30 ≈ 32 ». Vérifie le chiffre des unités avant tout arrondi à la dizaine.
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
