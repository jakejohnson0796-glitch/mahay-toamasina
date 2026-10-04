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

PROMPT_TRANSPORT_SANS_ANTISLASH = r"""
CONTRAT UNIQUE DU TUTEUR IA ET DU QUIZ IA — OBLIGATOIRE :

1. STRUCTURE
- Réponds en Markdown clair et pédagogique.
- Utilise des titres, listes et paragraphes normalement.
- Le code doit être dans un bloc Markdown de type ```python, ```sql, ```bash, etc.
- Les tableaux doivent rester de vrais tableaux Markdown avec des barres verticales.

2. MATHÉMATIQUES ET PHYSIQUE
- Le caractère antislash est interdit DANS LES FORMULES ET LE MARKUP MATH du tool-call JSON.
- Formule courte : [[MATH]]...[[/MATH]].
- Formule en bloc : [[DISPLAY]]...[[/DISPLAY]].
- Dans ces marqueurs, utilise uniquement une notation sans antislash :
  det(A)=ad-bc, x^2, a/b, x<=y, x>=y, 2 x 3, v=d/t.
- Pour une matrice, utilise toujours [a b ; c d] dans un marqueur.
- Pour plusieurs étapes, utilise un bloc [[DISPLAY]] avec des lignes séparées
  par ; entre les lignes matricielles ou par des expressions simples.
- N'utilise jamais le caractère antislash, une commande LaTeX ou un
  délimiteur LaTeX pour les mathématiques dans le JSON. Dans les blocs de
  code, utilise du code normal et laisse le serveur traiter le code comme du
  code, pas comme des mathématiques.
- Le serveur transformera les marqueurs en LaTeX après le parsing JSON.

3. CHIMIE
- Utilise [[CHEM]]...[[/CHEM]] pour les équations chimiques.
- Exemple : [[CHEM]]2H2 + O2 -> 2H2O[[/CHEM]]
- Exemple : [[CHEM]]Fe3+ + 3OH- -> Fe(OH)3[[/CHEM]]
- N'écris jamais une commande mhchem ou LaTeX dans le JSON.

4. QUALITÉ PÉDAGOGIQUE
- Vérifie les calculs, signes, unités, dimensions et résultats.
- Le Tuteur doit conserver une cohérence exacte entre explication, exemple,
  exercice et correction.
- Le Quiz doit avoir une seule bonne réponse et une explication qui démontre
  précisément cette réponse.
- Pour une matrice, ne crée jamais un tableau Markdown pour représenter les
  éléments de la matrice.
- Ne signale pas une question comme correcte si aucune option n'est correcte.

5. AUTRES DOMAINES
- Informatique : code complet dans des blocs de code.
- Comptabilité : montants avec espace pour les milliers, virgule décimale et
  unité Ar ; écritures et bilans en tableaux Markdown.
- Physique : équations en [[MATH]] ou [[DISPLAY]] et unités lisibles en texte
  mathématique simple.
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
