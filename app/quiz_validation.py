"""Validation locale des quizzes avant stockage ou correction."""
import re
from typing import Any

MAX_QUESTION_CHARS = 800
MAX_CHOIX_CHARS = 300
MAX_EXPLICATION_CHARS = 800
MAX_NOTION_CHARS = 100
MAX_TOTAL_CHARS = 60_000


def normaliser_math_texte(texte: str) -> str:
    """Rend les fragments LaTeX/Markdown envoyes par un modele lisibles
    dans l'interface sans dependre d'un moteur MathJax/KaTeX externe."""
    texte = str(texte or "").strip()
    if not texte:
        return ""

    fence = chr(96) * 3
    texte = texte.replace(fence, "")
    texte = texte.replace(r"\(", "").replace(r"\)", "")
    texte = texte.replace(r"\[", "").replace(r"\]", "")
    texte = texte.replace("$", "")

    def matrice(match):
        contenu = match.group(2)
        contenu = contenu.replace(r"\\", ";")
        lignes = []
        for ligne in contenu.split(";"):
            cellules = [c.strip() for c in ligne.split("&")]
            if any(cellules):
                lignes.append("  ".join(cellules))
        return "[ " + " ; ".join(lignes) + " ]" if lignes else "(" + contenu + ")"

    texte = re.sub(
        r"\\begin\{(pmatrix|bmatrix|vmatrix|matrix)\}(.*?)\\end\{\1\}",
        matrice,
        texte,
        flags=re.S,
    )

    replacements = [
        (r"\\times\b", " × "),
        (r"\\cdot\b", " · "),
        (r"\\pm\b", " ± "),
        (r"\\leq\b|\\le\b", " ≤ "),
        (r"\\geq\b|\\ge\b", " ≥ "),
        (r"\\neq\b", " ≠ "),
        (r"\\approx\b", " ≈ "),
        (r"\\in\b", " ∈ "),
        (r"\\notin\b", " ∉ "),
        (r"\\subseteq\b", " ⊆ "),
        (r"\\subset\b", " ⊂ "),
        (r"\\rightarrow\b|\\to\b", " → "),
        (r"\\Rightarrow\b", " ⇒ "),
        (r"\\Leftrightarrow\b|\\iff\b", " ⇔ "),
        (r"\\infty\b", " ∞ "),
        (r"\\pi\b", " π "),
        (r"\\alpha\b", " α "),
        (r"\\beta\b", " β "),
        (r"\\gamma\b", " γ "),
        (r"\\Delta\b", " Δ "),
        (r"\\lambda\b", " λ "),
        (r"\\mu\b", " μ "),
        (r"\\sigma\b", " σ "),
        (r"\\theta\b", " θ "),
        (r"\\det\s*\(", "det("),
        (r"\\ker\s*\(", "ker("),
        (r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1)/(\2)"),
        (r"\\sqrt\{([^{}]+)\}", r"√(\1)"),
    ]
    for motif, remplacement in replacements:
        texte = re.sub(motif, remplacement, texte)

    texte = re.sub(r"\^\{([^{}]+)\}", r"^(\1)", texte)
    texte = re.sub(r"_\{([^{}]+)\}", r"_(\1)", texte)
    texte = re.sub(r"\\([A-Za-z]+)", r"\1", texte)
    texte = texte.replace("{", "").replace("}", "")
    texte = re.sub(r"\*\*([^*]+)\*\*", r"\1", texte)
    texte = re.sub(r"__([^_]+)__", r"\1", texte)
    texte = re.sub(r"[ \t]+", " ", texte)
    texte = re.sub(r"\s+([,.;:!?])", r"\1", texte)
    return texte.strip()



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
