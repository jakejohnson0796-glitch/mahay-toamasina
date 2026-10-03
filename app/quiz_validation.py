"""Validation locale des quizzes avant stockage ou correction."""
import re
from typing import Any

MAX_QUESTION_CHARS = 800
MAX_CHOIX_CHARS = 300
MAX_EXPLICATION_CHARS = 800
MAX_NOTION_CHARS = 100
MAX_TOTAL_CHARS = 60_000


def normaliser_math_texte(texte: str) -> str:
    """Nettoie Markdown sans détruire la notation mathématique structurée."""
    texte = str(texte or "").strip()
    if not texte:
        return ""

    fence = chr(96) * 3
    texte = texte.replace(fence, "")
    texte = texte.replace(r"\\(", r"\(").replace(r"\\)", r"\)")
    texte = texte.replace(r"\\[", r"\[").replace(r"\\]", r"\]")
    texte = re.sub(r"\*\*([^*\n]+?)\*\*", r"\1", texte)
    texte = re.sub(r"__([^_\n]+?)__", r"\1", texte)

    # Matrices brutes : on les conserve en TeX pour le renderer.
    texte = re.sub(
        r"\[\s*([^\[\]\n;]+(?:;\s*[^\[\]\n;]+)+)\s*\]",
        lambda m: r"\[" + r"\begin{pmatrix}" + " \\\\ ".join(
            "&".join(part.strip().split()) for part in m.group(1).split(";")
        ) + r"\end{pmatrix}" + r"\]",
        texte,
    )

    texte = re.sub(r"[ \t]+", " ", texte)
    texte = re.sub(r"\s+([,.;:!?])", r"\1", texte)
    return texte.strip()



def rendre_math_html(texte: str):
    """Rend de façon sûre les fragments mathématiques usuels en HTML.

    Le quiz doit conserver les expressions en notation mathématique
    structurée : matrices, fractions, racines, indices et exposants.
    On ne transforme plus les matrices en texte ambigu du type
    "[ a b ; c d ]".
    """
    import html as _html
    import re as _re
    from markupsafe import Markup

    brut = str(texte or "").strip()
    if not brut:
        return Markup("")

    # Nettoyage léger du Markdown autour du contenu, sans détruire le TeX.
    fence = chr(96) * 3
    brut = brut.replace(fence, "")
    brut = brut.replace(r"\\(", r"\(").replace(r"\\)", r"\)")
    brut = brut.replace(r"\\[", r"\[").replace(r"\\]", r"\]")
    brut = _re.sub(r"\*\*([^*\n]+?)\*\*", r"\1", brut)

    math_pattern = _re.compile(
        r"(\$\$(?:.|\n)*?\$\$|\\\[(?:.|\n)*?\\\]|\\\((?:.|\n)*?\\\)"
        r"|\\begin\{(?:pmatrix|bmatrix|vmatrix|matrix)\}(?:.|\n)*?\\end\{(?:pmatrix|bmatrix|vmatrix|matrix)\})"
    )

    symbol_map = [
        (r"\\times\b", "×"),
        (r"\\cdot\b", "·"),
        (r"\\pm\b", "±"),
        (r"\\leq\b|\\le\b", "≤"),
        (r"\\geq\b|\\ge\b", "≥"),
        (r"\\neq\b", "≠"),
        (r"\\approx\b", "≈"),
        (r"\\infty\b", "∞"),
        (r"\\pi\b", "π"),
        (r"\\alpha\b", "α"),
        (r"\\beta\b", "β"),
        (r"\\gamma\b", "γ"),
        (r"\\Delta\b", "Δ"),
        (r"\\lambda\b", "λ"),
        (r"\\mu\b", "μ"),
        (r"\\sigma\b", "σ"),
        (r"\\theta\b", "θ"),
        (r"\\rightarrow\b|\\to\b", "→"),
        (r"\\Rightarrow\b", "⇒"),
        (r"\\Leftrightarrow\b|\\iff\b", "⇔"),
        (r"\\det\b", "det"),
        (r"\\ker\b", "ker"),
    ]

    def _math_inline(contenu: str) -> str:
        raw = contenu.strip()
        if raw.startswith("$") and raw.endswith("$"):
            raw = raw[2:-2]
        elif raw.startswith(r"\[") and raw.endswith(r"\]"):
            raw = raw[2:-2]
        elif raw.startswith(r"\(") and raw.endswith(r"\)"):
            raw = raw[2:-2]
        return _rendre_expression(raw)

    def _rendre_expression(raw: str) -> str:
        raw = raw.strip()
        matrix = _re.fullmatch(
            r"\\begin\{(pmatrix|bmatrix|vmatrix|matrix)\}(.*?)\\end\{\1\}",
            raw,
            flags=_re.S,
        )
        if matrix:
            contenu = matrix.group(2).strip()
            contenu = contenu.replace(r"\\\\", "\n")
            lignes = [x for x in contenu.split("\n") if x.strip()]
            rows = []
            for ligne in lignes:
                cellules = [c.strip() for c in ligne.split("&")]
                rows.append(
                    "<tr>" + "".join(
                        f"<td>{_html.escape(cell, quote=True)}</td>" for cell in cellules
                    ) + "</tr>"
                )
            return '<span class="math-matrix-wrap" aria-label="Matrice"><table class="math-matrix"><tbody>' + "".join(rows) + "</tbody></table></span>"

        safe = _html.escape(raw, quote=True)
        safe = _re.sub(
            r"\\frac\{([^{}]+)\}\{([^{}]+)\}",
            r'<span class="math-frac"><span class="math-num">\1</span><span class="math-den">\2</span></span>',
            safe,
        )
        safe = _re.sub(
            r"\\sqrt\{([^{}]+)\}",
            r'<span class="math-root">√<span class="math-root-body">\1</span></span>',
            safe,
        )
        safe = _re.sub(r"\^\{([^{}]+)\}", r"<sup>\1</sup>", safe)
        safe = _re.sub(r"_\{([^{}]+)\}", r"<sub>\1</sub>", safe)
        for motif, remplacement in symbol_map:
            safe = _re.sub(motif, remplacement, safe)
        safe = safe.replace(r"\,", " ")
        safe = _re.sub(r"\\([A-Za-z]+)", r"\1", safe)
        return safe

    morceaux = []
    derniere = 0
    for match in math_pattern.finditer(brut):
        normal = brut[derniere:match.start()]
        if normal:
            morceaux.append(_html.escape(normal, quote=True).replace("\n", "<br>"))
        expr = match.group(0)

        # Un environnement matriciel nu devient un affichage de matrice.
        display = expr.startswith("$") or expr.startswith(r"\[") or expr.startswith(r"\begin")
        classe = "math-display" if display else "math-inline"
        morceaux.append(f'<span class="{classe}">{_math_inline(expr)}</span>')
        derniere = match.end()

    reste = brut[derniere:]
    if reste:
        morceaux.append(_html.escape(reste, quote=True).replace("\n", "<br>"))

    return Markup("".join(morceaux))


class QuizValidationError(ValueError):
    pass


def valider_questions(questions: Any, expected_count: int | None = None) -> list[dict]:
    if not isinstance(questions, list):
        raise QuizValidationError("Le quiz doit etre une liste de questions.")
    if expected_count is not None and len(questions) != expected_count:
        raise QuizValidationError("Le nombre de questions est incorrect.")
    total = 0
    result: list[dict] = []
    for numero, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            raise QuizValidationError(f"La question {numero} est invalide.")
        texte = normaliser_math_texte(question.get("question", ""))
        choix = question.get("choix")
        explication = normaliser_math_texte(question.get("explication", ""))
        notion = normaliser_math_texte(question.get("notion", ""))
        index = question.get("index_bonne_reponse")
        if not texte or len(texte) > MAX_QUESTION_CHARS:
            raise QuizValidationError(f"Le texte de la question {numero} est invalide.")
        if not isinstance(choix, list) or not 3 <= len(choix) <= 5:
            raise QuizValidationError(f"La question {numero} doit avoir entre 3 et 5 choix.")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(choix):
            raise QuizValidationError(f"L'index de bonne reponse de la question {numero} est invalide.")
        if not explication or len(explication) > MAX_EXPLICATION_CHARS:
            raise QuizValidationError(f"L'explication de la question {numero} est invalide.")
        if notion and len(notion) > MAX_NOTION_CHARS:
            raise QuizValidationError(f"La notion de la question {numero} est trop longue.")
        choix_nettoyes = [normaliser_math_texte(c) for c in choix]
        if any(not c or len(c) > MAX_CHOIX_CHARS for c in choix_nettoyes):
            raise QuizValidationError(f"Un choix de la question {numero} est invalide.")
        signatures = [re.sub(r"\s+", " ", c).casefold() for c in choix_nettoyes]
        if len(set(signatures)) != len(signatures):
            raise QuizValidationError(f"Les choix de la question {numero} doivent etre distincts.")
        total += len(texte) + len(explication) + sum(len(c) for c in choix_nettoyes)
        if total > MAX_TOTAL_CHARS:
            raise QuizValidationError("Le quiz depasse la taille maximale autorisee.")
        result.append({
            "question": texte,
            "choix": choix_nettoyes,
            "index_bonne_reponse": index,
            "explication": explication,
            "notion": notion,
        })
    return result
