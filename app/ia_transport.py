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

PROMPT_TRANSPORT_SANS_ANTISLASH = r"""
TRANSPORT JSON SÛR — OBLIGATOIRE :
- Le caractère antislash est interdit dans les valeurs texte du tool-call JSON.
- Pour une formule courte, utilise [[MATH]]...[[/MATH]].
- Pour une formule en bloc, utilise [[DISPLAY]]...[[/DISPLAY]].
- Dans ces marqueurs, utilise une notation mathématique sans antislash :
  det(A)=ad-bc, x^2, a/b, x<=y, x>=y, [a b ; c d], 2 x 3.
- Pour une matrice, utilise toujours [a b ; c d] dans un marqueur.
- Ne mets jamais de balises Markdown de formule, de commande LaTeX ou de
  caractère antislash dans le JSON.
- Le serveur transforme automatiquement les marqueurs en vrai LaTeX après
  le parsing JSON. Le rendu final utilisera KaTeX.
- Le reste du texte peut rester en français et en Markdown simple.
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
    texte = re.sub(r"(?<![A-Za-z])(det)(?=\s*\()", _COMMANDES_SANS_ANTISLASH["det"], texte)
    texte = re.sub(r"(?<![A-Za-z])(sin)(?=\s*\()", _COMMANDES_SANS_ANTISLASH["sin"], texte)
    texte = re.sub(r"(?<![A-Za-z])(cos)(?=\s*\()", _COMMANDES_SANS_ANTISLASH["cos"], texte)
    texte = re.sub(r"(?<![A-Za-z])(tan)(?=\s*\()", _COMMANDES_SANS_ANTISLASH["tan"], texte)
    texte = re.sub(r"(?<![A-Za-z])(ln)(?=\s*\()", _COMMANDES_SANS_ANTISLASH["ln"], texte)
    texte = re.sub(r"(?<![A-Za-z])(log)(?=\s*\()", _COMMANDES_SANS_ANTISLASH["log"], texte)

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


def convertir_math_transport_texte(valeur: Any) -> str:
    texte = "" if valeur is None else str(valeur)

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
