"""Transport sûr des contenus IA avant rendu Markdown/KaTeX.

Le fournisseur IA peut produire du texte mathématique dans un tool-call JSON.
Pour éviter les erreurs de parsing JSON, on transporte les formules avec des
marqueurs ASCII sans antislash, puis on les reconvertit en LaTeX côté serveur.
"""
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

_COMMANDES_SANS_ANTISLASH = {
    "det": r"\det",
    "sin": r"\sin",
    "cos": r"\cos",
    "tan": r"\tan",
    "ln": r"\ln",
    "log": r"\log",
    "sqrt": r"\sqrt",
}


def _convertir_notation_math_sure(contenu: str) -> str:
    texte = str(contenu or "").strip()
    if not texte:
        return ""

    texte = texte.replace("×", r"\times ")
    texte = texte.replace("->", r"\to ")
    texte = re.sub(r"(?<![A-Za-z])(det)(?=\s*\()", lambda _match: _COMMANDES_SANS_ANTISLASH["det"], texte)
    texte = re.sub(r"(?<![A-Za-z])(sin)(?=\s*\()", lambda _match: _COMMANDES_SANS_ANTISLASH["sin"], texte)
    texte = re.sub(r"(?<![A-Za-z])(cos)(?=\s*\()", lambda _match: _COMMANDES_SANS_ANTISLASH["cos"], texte)
    texte = re.sub(r"(?<![A-Za-z])(tan)(?=\s*\()", lambda _match: _COMMANDES_SANS_ANTISLASH["tan"], texte)
    texte = re.sub(r"(?<![A-Za-z])(ln)(?=\s*\()", lambda _match: _COMMANDES_SANS_ANTISLASH["ln"], texte)
    texte = re.sub(r"(?<![A-Za-z])(log)(?=\s*\()", lambda _match: _COMMANDES_SANS_ANTISLASH["log"], texte)

    # Matrice transport : [a b ; c d] -> pmatrix KaTeX.
    match = re.fullmatch(
        r"\[\s*([^\[\]\n]+(?:;\s*[^\[\]\n]+)+)\s*\]",
        texte,
    )
    if match:
        lignes = []
        for ligne in match.group(1).split(";"):
            cellules = [c for c in re.split(r"\s+", ligne.strip()) if c]
            if cellules:
                lignes.append(" & ".join(cellules))
        if len(lignes) >= 2:
            return r"\begin{pmatrix}" + r" \\ ".join(lignes) + r"\end{pmatrix}"

    return texte


def _normaliser_sauts_de_ligne_litteraux(texte: str) -> str:
    """Convertit les \n littéraux produits par certains modèles en vrais retours.

    On cible uniquement \n suivis d'une majuscule, d'un espace ou d'un
    antislash suivi d'une majuscule. Cela évite de transformer des commandes
    LaTeX valides comme \nabla.
    """
    texte = re.sub(r"\\n(?=[A-ZÀ-ÖØ-Þ])", "\n", texte)
    texte = re.sub(r"\\n(?=\\[A-ZÀ-ÖØ-Þ])", "\n", texte)
    texte = re.sub(r"\\n(?=\\s)", "\n", texte)
    return texte


_COMMANDES_LATEX_NUES_RE = re.compile(
    r"\\(?:det|frac|dfrac|tfrac|sqrt|sum|prod|int|lim|ln|log|sin|cos|tan|cot|exp|partial|nabla|vec|mathbf|mathbb|mathrm|text|alpha|beta|gamma|delta|theta|lambda|mu|pi|sigma|infty)\b"
    r"|\\begin\{(?:bmatrix|pmatrix|Bmatrix|vmatrix|Vmatrix|matrix|cases|aligned|array)\}"
)

def _normaliser_latex_nu(texte: str) -> str:
    """Compatibilité conservatrice pour un LaTeX nu mal formé.

    Les zones déjà délimitées et les zones de code sont masquées avant tout
    traitement : un bloc LaTeX multiligne est donc toujours atomique.
    """
    source = str(texte or "")
    zones: list[str] = []

    def masquer(match: re.Match[str]) -> str:
        index = len(zones)
        zones.append(match.group(0))
        return f"__GMATHZONE_{index}__"

    # Les zones de code sont prioritaires : un code inline peut lui-même
    # contenir des délimiteurs LaTeX et ne doit jamais être extrait comme math.
    source = re.sub(r"(?s)\x60\x60\x60.*?\x60\x60\x60", masquer, source)
    source = re.sub(r"\x60[^\x60\n]*\x60", masquer, source)
    source = re.sub(r"(?s)\\\[.*?\\\]|\\\(.*?\\\)", masquer, source)

    resultat = []
    for ligne in source.splitlines():
        if not ligne.strip():
            resultat.append(ligne)
            continue

        match = _COMMANDES_LATEX_NUES_RE.search(ligne)
        if not match:
            resultat.append(ligne)
            continue

        avant = ligne[:match.start()]
        formule_et_suite = ligne[match.start():].strip()
        fin = re.search(r"[.!?](?=\s+[A-ZÀ-ÖØ-Þ]|$)", formule_et_suite)
        suffixe = ""
        if fin:
            indice_fin = fin.end()
            suffixe = formule_et_suite[indice_fin:]
            formule_et_suite = formule_et_suite[:indice_fin]

        formule = formule_et_suite.strip()
        if formule.endswith((".", "!", "?")):
            ponctuation = formule[-1]
            formule = formule[:-1].rstrip()
            suffixe = ponctuation + suffixe

        if not formule:
            resultat.append(ligne)
            continue

        affichage = (
            r"\[" + formule + r"\]"
            if r"\begin{" in formule
            else r"\(" + formule + r"\)"
        )
        resultat.append(avant + affichage + suffixe)

    resultat_texte = "\n".join(resultat)
    for index, zone in enumerate(zones):
        resultat_texte = resultat_texte.replace(f"__GMATHZONE_{index}__", zone)
    return resultat_texte

PROMPT_TRANSPORT_SANS_ANTISLASH = REGLES_FORMAT


def convertir_math_transport_texte(valeur: Any) -> str:
    texte = "" if valeur is None else str(valeur)
    # Les chaînes JSON valides ont déjà été décodées par json.loads().
    # Aucune normalisation des sauts de ligne n'est appliquée ici.
    texte = _normaliser_latex_nu(texte)

    def display(match: re.Match[str]) -> str:
        return r"\[" + _convertir_notation_math_sure(match.group(1)) + r"\]"

    def inline(match: re.Match[str]) -> str:
        return r"\(" + _convertir_notation_math_sure(match.group(1)) + r"\)"

    # Compatibilité avec les données historiques et les modèles qui utilisent
    # encore les marqueurs de transport dans des réponses déjà stockées.
    texte = re.sub(
        r"\[\[DISPLAY\]\](.*?)\[\[/DISPLAY\]\]",
        display,
        texte,
        flags=re.DOTALL,
    )
    texte = re.sub(
        r"\[\[MATH\]\](.*?)\[\[/MATH\]\]",
        inline,
        texte,
        flags=re.DOTALL,
    )
    texte = re.sub(
        r"\[\[CHEM\]\](.*?)\[\[/CHEM\]\]",
        lambda match: r"\(\ce{" + match.group(1).strip() + r"}\)",
        texte,
        flags=re.DOTALL,
    )
    return texte


def normaliser_structure_quiz(questions: list[Mapping[str, Any]] | None) -> list[dict]:
    resultat = []
    for question in questions or []:
        item = dict(question)
        item["question"] = convertir_math_transport_texte(item.get("question", ""))
        item["choix"] = [
            convertir_math_transport_texte(choix) for choix in (item.get("choix") or [])
        ]
        item["explication"] = convertir_math_transport_texte(item.get("explication", ""))
        resultat.append(item)
    return resultat


def normaliser_structure_tuteur(reponse: Mapping[str, Any] | None) -> dict[str, str]:
    source = reponse or {}
    return {
        "explication": convertir_math_transport_texte(source.get("explication", "")),
        "exemple": convertir_math_transport_texte(source.get("exemple", "")),
        "exercice": convertir_math_transport_texte(source.get("exercice", "")),
        "correction": convertir_math_transport_texte(source.get("correction", "")),
    }
