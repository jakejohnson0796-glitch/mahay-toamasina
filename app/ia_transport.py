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
    r"\\(?:det|frac|dfrac|tfrac|sqrt|sum|prod|int|lim|ln|log|sin|cos|tan|cot|exp|partial|nabla|vec|mathbf|mathbb|mathrm|text|times|cdot|pm|leq|geq|neq|approx|infty|alpha|beta|gamma|delta|theta|lambda|mu|pi|sigma)\\b"
    r"|\\begin\\{(?:bmatrix|pmatrix|Bmatrix|vmatrix|Vmatrix|matrix|cases|aligned|array)\\}"
)

def _normaliser_latex_nu(texte: str) -> str:
    """Encapsule les commandes LaTeX nues dans des délimiteurs valides."""
    lignes = str(texte or "").splitlines()
    resultat = []
    dans_code = False

    for ligne in lignes:
        if ligne.strip().startswith("```"):
            dans_code = not dans_code
            resultat.append(ligne)
            continue
        if dans_code or not ligne.strip():
            resultat.append(ligne)
            continue
        if "\\(" in ligne or "\\[" in ligne or "[[MATH]]" in ligne or "[[DISPLAY]]" in ligne:
            resultat.append(ligne)
            continue

        match = _COMMANDES_LATEX_NUES_RE.search(ligne)
        if not match:
            resultat.append(ligne)
            continue

        avant = ligne[:match.start()]
        formule_et_suite = ligne[match.start():].strip()
        fin = re.search(r"[.!?](?=\\s+[A-ZÀ-ÖØ-Þ]|$)", formule_et_suite)
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
            if "\\begin{" in formule
            else r"\(" + formule + r"\)"
        )
        resultat.append(avant + affichage + suffixe)

    return "\n".join(resultat)

def convertir_math_transport_texte(valeur: Any) -> str:
    texte = "" if valeur is None else str(valeur)
    # MODIF : corrige les réponses Tuteur/Quiz qui transportent encore des
    # retours à la ligne sous forme littérale \\n.
    texte = _normaliser_sauts_de_ligne_litteraux(texte)
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
