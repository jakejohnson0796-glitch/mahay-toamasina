"""Transport texte brut des contenus IA.

Le modèle peut produire du LaTeX, du Markdown ou des marqueurs historiques.
Ce module ne doit PLUS transformer le contenu pédagogique : la mise en forme
est réalisée exclusivement par app/static/js/rendu_ia.js dans le navigateur.

La fonction convertir_math_transport_texte est conservée pour compatibilité
avec les anciens imports/tests, mais elle est désormais volontairement
identitaire.
"""

from __future__ import annotations

import re
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
- INTERDICTION DE BACKTICKS MATHS : n'entoure jamais une formule, une fraction, une égalité, un calcul ou une puissance avec des backticks Markdown. Les backticks sont réservés au code informatique réel. Même dans une liste, écris \\(123456=156\\times789+372\\) en LaTeX, pas `123456=156`\\times789+372.
- FRACTIONS : écris toujours le numérateur et le dénominateur explicitement avec \\(\\frac{a}{b}\\) ou \\[\\frac{a}{b}\\]. N'écris jamais les deux nombres collés, ni seulement la fraction visuelle sans commandes LaTeX. Pour \\(\\frac{123456000}{789000}\\), conserve bien les deux nombres séparés par `\\frac{...}{...}`.
- PUISSANCES : écris chaque exposant explicitement, par exemple \\(10^{3}\\), jamais `103` pour représenter dix puissance trois. N'aplatis jamais les indices/exposants en nombres ordinaires.
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
- Vérifie calculs, signes, unités, dimensions, indices et résultats. Pour l'algorithme d'Euclide, chaque ligne \\(a=bq+r\\) doit vérifier numériquement l'égalité et \\(0\\le r<b\\); contrôle particulièrement les restes. Exemple vérifié : \\(123456=156\\times789+372\\), et non un reste différent.
- Avant de renvoyer le JSON, relis les formules dans leur contexte : aucune commande \\times ne doit rester hors délimiteurs mathématiques, aucune fraction ne doit être collée en texte brut, et les équations doivent être correctes.
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


_MOTIF_IDENTITE_EUCLIDE = re.compile(
    r"(?P<dividende>\d{1,18})\s*=\s*(?P<quotient>\d{1,18})\s*"
    r"(?:\\times|×|x|\t?imes)\s*(?P<diviseur>\d{1,18})\s*"
    r"\+\s*(?P<reste>\d{1,18})"
)
_CONTEXTE_EUCLIDE = re.compile(r"\beuclide\b|\bpgcd\b", re.IGNORECASE)


def _contexte_euclide_present(*textes: str) -> bool:
    return any(_CONTEXTE_EUCLIDE.search(str(texte or "")) for texte in textes)


def corriger_identites_euclide(texte: Any, *, contexte_euclide: bool = False) -> str:
    """Corrige et met au format LaTeX les divisions euclidiennes identifiables.

    La correction n'est activée que si le contenu parle du PGCD/de l'algorithme
    d'Euclide. Elle recalcule quotient et reste, au lieu de faire confiance aux
    nombres fournis par le modèle. Elle répare aussi les délimiteurs de code
    inline qui coupent une formule et la tabulation JSON remplaçant le début
    de la commande LaTeX de multiplication. Les autres textes restent inchangés.
    """
    source = convertir_math_transport_texte(texte)
    if not (contexte_euclide or _CONTEXTE_EUCLIDE.search(source)):
        return source

    resultat = []
    for ligne in source.splitlines(keepends=True):
        fin_ligne = ""
        contenu_ligne = ligne
        if contenu_ligne.endswith("\r\n"):
            contenu_ligne, fin_ligne = contenu_ligne[:-2], "\r\n"
        elif contenu_ligne.endswith(("\n", "\r")):
            contenu_ligne, fin_ligne = contenu_ligne[:-1], contenu_ligne[-1:]

        # Retirer les délimiteurs de code uniquement sur une ligne qui contient
        # réellement une identité euclidienne reconnue.
        candidate = contenu_ligne.replace(chr(96), "")
        match = _MOTIF_IDENTITE_EUCLIDE.search(candidate)
        if not match:
            resultat.append(ligne)
            continue

        dividende = int(match.group("dividende"))
        diviseur = int(match.group("diviseur"))
        if diviseur <= 0 or dividende < 0:
            resultat.append(ligne)
            continue

        quotient_correct, reste_correct = divmod(dividende, diviseur)
        quotient_recu = int(match.group("quotient"))
        reste_recu = int(match.group("reste"))
        operator_corrompu = "\t" in contenu_ligne or chr(96) in contenu_ligne
        if (
            quotient_correct == quotient_recu
            and reste_correct == reste_recu
            and not operator_corrompu
        ):
            resultat.append(ligne)
            continue

        formule = (
            rf"\({dividende}={quotient_correct}\times{diviseur}+{reste_correct}\)"
        )
        candidate = candidate[:match.start()] + formule + candidate[match.end():]
        resultat.append(candidate + fin_ligne)

    return "".join(resultat)


def normaliser_structure_quiz(questions: list[Mapping[str, Any]] | None) -> list[dict]:
    """Copie la structure du quiz sans toucher aux champs pédagogiques."""
    resultat: list[dict] = []
    for question in questions or []:
        item = dict(question)
        question_brute = convertir_math_transport_texte(item.get("question", ""))
        explication_brute = convertir_math_transport_texte(item.get("explication", ""))
        choix_bruts = [
            convertir_math_transport_texte(choix)
            for choix in (item.get("choix") or [])
        ]
        contexte_euclide = _contexte_euclide_present(
            question_brute, explication_brute, *choix_bruts
        )
        item["question"] = corriger_identites_euclide(
            question_brute, contexte_euclide=contexte_euclide
        )
        item["choix"] = [
            corriger_identites_euclide(choix, contexte_euclide=contexte_euclide)
            for choix in choix_bruts
        ]
        item["explication"] = corriger_identites_euclide(
            explication_brute, contexte_euclide=contexte_euclide
        )
        resultat.append(item)
    return resultat


def normaliser_structure_tuteur(
    reponse: Mapping[str, Any] | None,
) -> dict[str, str]:
    """Copie les quatre sections du Tuteur sans transformation de contenu."""
    source = reponse or {}
    sections = {
        "explication": convertir_math_transport_texte(source.get("explication", "")),
        "exemple": convertir_math_transport_texte(source.get("exemple", "")),
        "exercice": convertir_math_transport_texte(source.get("exercice", "")),
        "correction": convertir_math_transport_texte(source.get("correction", "")),
    }
    contexte_euclide = _contexte_euclide_present(*sections.values())
    return {
        cle: corriger_identites_euclide(valeur, contexte_euclide=contexte_euclide)
        for cle, valeur in sections.items()
    }
