"""Routage adaptatif des verifications de quiz.

Le quiz reste rapide : ce module ne fait que calculer localement le niveau
de verification a appliquer apres livraison.
"""
import re
from typing import Dict, List


STRATEGIE_LEGERE = "legere"
STRATEGIE_STANDARD = "standard"
STRATEGIE_RENFORCEE = "renforcee"


_MOTS_MATHS = re.compile(
    r"\b(calcul|calculer|equation|équation|derivee|dérivée|integrale|intégrale|"
    r"probabilite|probabilité|statistique|pourcentage|fraction|formule|theoreme|"
    r"théorème|physique|chimie|coefficient|racine|matrice|vecteur)\b",
    re.IGNORECASE,
)


def analyser_risque(
    questions: List[Dict],
    *,
    matiere: str,
    niveau: str,
    difficulte: str,
    signaux_recurrents: int = 0,
) -> Dict:
    """Retourne score, strategie et raisons explicables."""
    score = 0
    raisons: List[str] = []

    difficulte_norm = (difficulte or "").strip().lower()
    if difficulte_norm == "difficile":
        score += 2
        raisons.append("difficulte_difficile")
    elif difficulte_norm == "moyen":
        score += 1

    if len(questions) >= 15:
        score += 1
        raisons.append("quiz_long")

    texte_questions = " ".join(
        str(q.get("question") or "") + " " + " ".join(str(x) for x in (q.get("choix") or []))
        for q in questions
    )
    if _MOTS_MATHS.search(texte_questions):
        score += 2
        raisons.append("contenu_technique")

    if signaux_recurrents >= 3:
        score += 2
        raisons.append("erreurs_recurrentes")
    elif signaux_recurrents > 0:
        score += 1
        raisons.append("historique_erreurs")

    # Matiere inconnue ou niveau atypique : petite marge de securite.
    if not (matiere or "").strip() or not (niveau or "").strip():
        score += 1
        raisons.append("contexte_incomplet")

    if score <= 1:
        strategie = STRATEGIE_LEGERE
    elif score <= 3:
        strategie = STRATEGIE_STANDARD
    else:
        strategie = STRATEGIE_RENFORCEE

    return {
        "score": score,
        "strategie": strategie,
        "raisons": raisons,
    }
