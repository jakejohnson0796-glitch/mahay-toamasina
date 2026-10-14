r"""Lecture stricte et conservatrice du JSON produit par les modèles IA.

Règle principale : json.loads() est toujours tenté en premier et, lorsqu'il
réussit, la chaîne décodée est retournée sans aucune réparation métier.

Une récupération n'est utilisée que pour un JSON réellement invalide. Elle
ne reconnaît que des commandes LaTeX appartenant à une liste blanche explicite.
"""

from __future__ import annotations

import json
import re
from typing import Any


_COMMANDES_LATEX_AUTORISEES = {
    "frac", "dfrac", "tfrac", "sqrt", "sum", "prod", "int", "lim",
    "det", "sin", "cos", "tan", "cot", "exp", "ln", "log", "partial",
    "nabla", "vec", "mathbf", "mathbb", "mathrm", "text", "begin", "end",
    "alpha", "beta", "gamma", "delta", "theta", "lambda", "mu", "nu", "pi",
    "rho", "sigma", "tau", "phi", "omega", "times", "cdot", "neq", "le",
    "ge", "leq", "geq", "approx", "pm", "forall", "exists", "left", "right",
    "ce", "infty", "in", "mathcal", "operatorname", "displaystyle", "textstyle",
    "scriptstyle", "textbf", "textit", "texttt", "textnormal", "emph", "overline",
    "underline", "widehat", "widetilde", "binom", "dbinom", "tbinom", "big", "Big",
    "bigl", "bigr", "Bigl", "Bigr", "bigg", "Bigg", "rangle", "langle", "rvert",
    "lvert", "nexists", "neg", "notin", "subseteq", "supseteq", "rightarrow",
    "leftarrow", "leftrightarrow", "Longrightarrow", "Longleftrightarrow",
}



def _reparer_collisions_escapes_json_latex(texte: str) -> str:
    """Préserve les commandes LaTeX qui ressemblent à des escapes JSON valides.

    Dans un JSON mal échappé, \frac peut être lu comme form-feed + rac,
    \text comme tabulation + ext, \nabla comme saut de ligne + abla,
    \rho comme retour chariot + ho ou \beta comme backspace + eta.
    Ces séquences sont valides du point de vue JSON : le parseur strict ne
    déclenche donc pas naturellement le réparateur historique.

    Le scanner ne modifie que des commandes en liste blanche, à l'intérieur
    des chaînes JSON et lorsqu'un seul antislash les introduit. Les doubles
    antislashs JSON, les guillemets échappés et les contrôles ordinaires restent
    intacts.
    """
    sortie: list[str] = []
    dans_chaine = False
    i = 0

    while i < len(texte):
        caractere = texte[i]

        if not dans_chaine:
            sortie.append(caractere)
            if caractere == '"':
                dans_chaine = True
            i += 1
            continue

        if caractere == '"':
            sortie.append(caractere)
            dans_chaine = False
            i += 1
            continue

        if caractere != "\\":
            sortie.append(caractere)
            i += 1
            continue

        suivant = texte[i + 1] if i + 1 < len(texte) else ""

        # Une paire d'antislashs est déjà correctement échappée en JSON.
        if suivant == "\\":
            sortie.extend(["\\", "\\"])
            i += 2
            continue

        if suivant.isalpha():
            match = re.match(r"[A-Za-z]+", texte[i + 1:])
            commande = match.group(0) if match else ""
            if commande in _COMMANDES_LATEX_AUTORISEES:
                sortie.extend(["\\", "\\", commande])
                i += 1 + len(commande)
                continue

        # Sinon, préserver les escapes JSON standard, notamment les vrais
        # sauts de ligne, tabulations, guillemets et séquences Unicode.
        if suivant in '"\\/bfnrt':
            sortie.extend(["\\", suivant])
            i += 2
            continue

        if suivant == "u" and i + 5 < len(texte):
            code = texte[i + 2:i + 6]
            if re.fullmatch(r"[0-9A-Fa-f]{4}", code):
                sortie.extend(["\\", "u", code])
                i += 6
                continue

        # Le cas n'est ni une commande autorisée ni un escape JSON standard.
        sortie.append("\\")
        i += 1

    return "".join(sortie)


def _reparer_antislashs_latex(texte: str) -> str:
    """Répare uniquement des commandes LaTeX explicitement autorisées.

    Cette fonction n'est appelée qu'après l'échec de json.loads(). Les escapes
    JSON valides (\n, \t, \r, \b, \f, \\, \/, \") restent donc intacts.
    """
    sortie: list[str] = []
    dans_chaine = False
    i = 0

    while i < len(texte):
        caractere = texte[i]

        if caractere == '"':
            echappe = False
            j = i - 1
            while j >= 0 and texte[j] == "\\":
                echappe = not echappe
                j -= 1
            if not echappe:
                dans_chaine = not dans_chaine
            sortie.append(caractere)
            i += 1
            continue

        if not dans_chaine or caractere != "\\":
            sortie.append(caractere)
            i += 1
            continue

        suivant = texte[i + 1] if i + 1 < len(texte) else ""

        if suivant.isalpha():
            match = re.match(r"[A-Za-z]+", texte[i + 1:])
            commande = match.group(0) if match else ""
            if commande in _COMMANDES_LATEX_AUTORISEES:
                sortie.extend(["\\", "\\", commande])
                i += 1 + len(commande)
                continue

        if suivant in '"\\/bfnrt':
            sortie.extend(["\\", suivant])
            i += 2
            continue

        if suivant == "u" and i + 5 < len(texte):
            code = texte[i + 2:i + 6]
            if re.fullmatch(r"[0-9A-Fa-f]{4}", code):
                sortie.extend(["\\", "u", code])
                i += 6
                continue

        # Délimiteurs LaTeX non alphabétiques : uniquement dans une récupération
        # d'un JSON déjà invalide.
        if suivant in "[]()":
            sortie.extend(["\\", "\\", suivant])
            i += 2
            continue

        # Séquence inconnue : ne pas l'inventer comme LaTeX.
        sortie.append("\\")
        i += 1

    return "".join(sortie)


def charger_json_ia(texte_brut: str | bytes | bytearray | Any) -> Any:
    """Charge un JSON IA sans altérer une sortie JSON valide."""
    if isinstance(texte_brut, (dict, list, int, float, bool)) or texte_brut is None:
        return texte_brut

    if isinstance(texte_brut, (bytes, bytearray)):
        texte = bytes(texte_brut).decode("utf-8")
    else:
        texte = str(texte_brut)

    # Étape A : réparer d'abord les collisions connues entre LaTeX et les
    # escapes JSON valides, puis effectuer un json.loads strict.
    texte_prepare = _reparer_collisions_escapes_json_latex(texte)
    try:
        return json.loads(texte_prepare)
    except json.JSONDecodeError as erreur_stricte:
        # Conserver l'exception hors du bloc except : Python détruit la variable
        # d'exception à la sortie du bloc pour éviter un cycle de références.
        erreur_json = erreur_stricte

    # Étape B/C : récupération ciblée si le JSON reste réellement invalide.
    repare = _reparer_antislashs_latex(texte_prepare)
    if repare == texte_prepare:
        raise erreur_json

    try:
        return json.loads(repare)
    except json.JSONDecodeError:
        raise erreur_json
