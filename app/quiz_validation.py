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
    texte = re.sub(r"^\s*#{1,6}\s+", "", texte, flags=re.MULTILINE)

    # Les sorties IA peuvent parfois encapsuler une matrice dans un tableau
    # Markdown. On les transforme en vrai bloc matriciel avant stockage.
    lignes_source = texte.splitlines()
    lignes_nettoyees = []
    i = 0

    def est_separateur_tableau(ligne: str) -> bool:
        morceaux = [c.strip().replace(":", "") for c in ligne.strip().strip("|").split("|")]
        return len(morceaux) >= 2 and all(morceau and set(morceau) <= {"-"} for morceau in morceaux)

    def cellules_tableau(ligne: str) -> list[str]:
        morceaux = [c.strip() for c in ligne.strip().strip("|").split("|")]
        return [re.sub(r"\*\*([^*]+?)\*\*", r"\1", c) for c in morceaux]

    while i < len(lignes_source):
        courant = lignes_source[i].strip()
        if "|" in courant and i + 1 < len(lignes_source) and est_separateur_tableau(lignes_source[i + 1]):
            lignes_tableau = [cellules_tableau(courant)]
            j = i + 2
            while j < len(lignes_source):
                suivant = lignes_source[j].strip()
                if not suivant or "|" not in suivant:
                    break
                lignes_tableau.append(cellules_tableau(suivant))
                j += 1

            etendues = []
            for ligne in lignes_tableau:
                valeurs = []
                for cellule in ligne:
                    # Exemple courant produit par les modèles :
                    # "| 3 | 6\\\\ 9 | 12 |" -> [["3", "6"], ["9", "12"]]
                    parties = [p.strip() for p in re.split(r"\\+\s*", cellule) if p.strip()]
                    valeurs.extend(parties or [cellule])
                etendues.append(valeurs)

            # Une matrice peut etre aplatie dans une seule ligne du
            # tableau Markdown. Reconstruit les matrices carrees (2x2, 3x3,
            # 4x4, ...) quand le nombre total de cellules est un carre parfait.
            if len(etendues) == 1 and etendues[0]:
                total_cellules = len(etendues[0])
                taille = int(total_cellules ** 0.5)
                if taille >= 2 and taille * taille == total_cellules:
                    flat = etendues[0]
                    etendues = [
                        flat[index:index + taille]
                        for index in range(0, total_cellules, taille)
                    ]

            if (
                len(etendues) >= 2
                and etendues[0]
                and all(len(ligne) == len(etendues[0]) for ligne in etendues)
            ):
                lignes_tex = ["&".join(ligne) for ligne in etendues]
                lignes_nettoyees.append(
                    r"\[" + r"\begin{pmatrix}" + r"\\ ".join(lignes_tex) + r"\end{pmatrix}" + r"\]"
                )
                i = j
                continue

        lignes_nettoyees.append(lignes_source[i])
        i += 1

    texte = "\n".join(lignes_nettoyees)

    # Matrices JSON/Python: [[1,2],[3,4]] -> \\[\\begin{pmatrix}1&2\\\\3&4\\end{pmatrix}\\]
    def matrice_liste(match):
        lignes_brutes = re.findall(r"\[([^\[\]]+)\]", match.group(1))
        lignes = []
        for ligne in lignes_brutes:
            cellules = [c.strip() for c in ligne.split(",")]
            if cellules:
                lignes.append("&".join(cellules))
        if len(lignes) >= 2:
            return r"\[" + r"\begin{pmatrix}" + r"\\ ".join(lignes) + r"\end{pmatrix}" + r"\]"
        return match.group(0)

    texte = re.sub(
        r"(\[\s*\[[^\]]+\](?:\s*,\s*\[[^\]]+\])+\s*\])",
        matrice_liste,
        texte,
    )

    # Les choix peuvent arriver avec leur propre préfixe A./B./C./D.
    # alors que le template affiche déjà la lettre. On retire uniquement
    # les préfixes clairement identificables, sans toucher aux expressions
    # comme A+B ou A=B.
    texte = re.sub(r"^\s*[A-F][.)\-:]\s+", "", texte)
    texte = re.sub(
        r"^\s*[A-F](?=(?:Il\b|La\b|Le\b|Les\b|Une\b|Un\b|Ce\b|Cette\b|Tout\b|Toute\b|Aucun\b|Aucune\b|Existe\b|Pour\b|Soit\b|Si\b|On\b))",
        "",
        texte,
        flags=re.IGNORECASE,
    )

    # Certains retours JSON/Markdown doublent les antislashs TeX.
    texte = re.sub(r"\\\\+([A-Za-z]+)", r"\\\1", texte)

    # Matrices brutes : on les conserve en TeX pour le renderer.
    texte = re.sub(
        r"\[\s*([^\[\]\n;]+(?:;\s*[^\[\]\n;]+)+)\s*\]",
        lambda m: r"\[" + r"\begin{pmatrix}" + " \\\\ ".join(
            "&".join(part.strip().split()) for part in m.group(1).split(";")
        ) + r"\end{pmatrix}" + r"\]",
        texte,
    )

    texte = re.sub(r"[ \t]+", " ", texte)
    # Symboles mathematiques courants : normalises des le stockage
    # pour eviter que certains navigateurs ou templates affichent les
    # commandes TeX brutes.
    symboles = [
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
    for motif, remplacement in symboles:
        texte = re.sub(motif, remplacement, texte)

    texte = re.sub(r"\s+([,.;:])", r"\1", texte)
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

    # Reapplique la normalisation au moment du rendu pour que les anciens
    # quizzes stockes avant la correction profitent eux aussi du formatage.
    brut = normaliser_math_texte(texte)
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

        def matrice_html(match):
            contenu = match.group(2).strip()
            # Les modeles peuvent produire plusieurs antislashs pour une
            # separation de ligne de matrice.
            contenu = _re.sub(r"\\\\{2,}\\s*", "\n", contenu)
            lignes = [x.strip() for x in contenu.split("\n") if x.strip()]
            rows = []
            for ligne in lignes:
                cellules = [c.strip() for c in ligne.split("&")]
                rows.append(
                    "<tr>" + "".join(
                        f"<td>{_html.escape(cell, quote=True)}</td>" for cell in cellules
                    ) + "</tr>"
                )
            return (
                '<span class="math-matrix-wrap" aria-label="Matrice"><table class="math-matrix"><tbody>'
                + "".join(rows)
                + "</tbody></table></span>"
            )

        safe = _html.escape(raw, quote=True)

        # Une matrice peut etre integree dans une expression plus longue,
        # par exemple "\\[A=\\begin{pmatrix}...\\end{pmatrix}\\]".
        safe = _re.sub(
            r"\\begin\{(pmatrix|bmatrix|vmatrix|matrix)\}(.*?)\\end\{\1\}",
            matrice_html,
            safe,
            flags=_re.S,
        )

        safe = _re.sub(
            r"\\mathbf\{([^{}]+)\}",
            r"<strong>\1</strong>",
            safe,
        )
        safe = _re.sub(
            r"\\mathrm\{([^{}]+)\}",
            r'<span class="math-rm">\1</span>',
            safe,
        )
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
        safe = safe.replace(r"\\,", " ")
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


def _verifier_coherence_explicative(
    choix_nettoyes: list[str],
    index_bonne_reponse: int,
    explication: str,
) -> None:
    """Bloque les contradictions explicites entre correction et QCM."""
    texte = normaliser_math_texte(explication).casefold()
    if not texte:
        return

    # Un QCM ne peut pas être publié si son explication reconnait elle-même
    # qu'aucune option ne répond à la question.
    contradictions = (
        r"aucun(?:e)?\s+des\s+(?:réponses|choix|options)",
        r"aucun(?:e)?\s+(?:réponse|choix|option)\s+(?:ne\s+)?(?:correspond|convient|est\s+correct)",
        r"aucun(?:e)?\s+des\s+(?:réponses|choix|options)\s+(?:proposé|proposées|fournis|fournies)",
        r"(?:il\s+faut|on\s+doit)\s+(?:corriger|ajouter|inclure|modifier)\b.*\b(?:choix|réponse)",
    )
    if any(re.search(motif, texte, flags=re.IGNORECASE) for motif in contradictions):
        raise QuizValidationError(
            "L'explication indique que les choix proposés ne contiennent pas la bonne réponse."
        )

    # Contrôle explicite d'un label : « la bonne réponse est B ».
    match_label = re.search(
        r"\b(?:la\s+)?bonne\s+r[ée]ponse\s*(?:est|:)\s*([A-F])\b",
        texte,
        flags=re.IGNORECASE,
    )
    if match_label:
        lettre = match_label.group(1).upper()
        attendu = "ABCDEF".index(lettre)
        if attendu != index_bonne_reponse:
            raise QuizValidationError(
                f"L'explication désigne {lettre} comme bonne réponse alors que l'index pointe vers "
                f"{'ABCDEF'[index_bonne_reponse]}."
            )

    # Contrôle simple d'une valeur courte : « la bonne réponse est 5 ».
    # On ne force la comparaison que si la valeur est courte et figure
    # clairement comme un choix autonome.
    match_valeur = re.search(
        r"\b(?:la\s+)?bonne\s+r[ée]ponse\s*(?:est|:)\s*([^,.;\n]{1,40})",
        texte,
        flags=re.IGNORECASE,
    )
    if match_valeur:
        valeur = normaliser_math_texte(match_valeur.group(1)).strip(" .:;")
        if valeur and len(valeur) <= 20:
            normalises = {
                re.sub(r"\s+", " ", c.casefold()).strip(" .")
                for c in choix_nettoyes
            }
            valeur_norm = re.sub(r"\s+", " ", valeur.casefold()).strip(" .")
            correspondants = [
                i for i, c in enumerate(normalises)
                if c == valeur_norm
            ]
            # Seulement lorsque l'expression correspond exactement à un
            # choix existant : cela évite les faux positifs sur des phrases
            # longues comme « la bonne réponse est la propriété... ».
            if correspondants and correspondants != [index_bonne_reponse]:
                raise QuizValidationError(
                    "L'explication désigne un choix différent de l'index de bonne réponse."
                )


def _normaliser_choix(choix: Any, index: int) -> str:
    """Normalise un choix QCM et retire seulement un prefixe evident."""
    texte = normaliser_math_texte(choix)
    if not texte:
        return ""

    label = "ABCDEF"[index] if 0 <= index < 6 else ""
    if not label or not texte.startswith(label) or len(texte) == 1:
        return texte

    suite = texte[1:]
    if suite.startswith(label):
        return suite

    if suite.startswith("|"):
        return suite

    if re.match(
        r"^(?:[=+\-×*/()\[\]\{\}]|\d|\\|"
        r"[α-ωΑ-Ω]|"
        r"Il\b|La\b|Le\b|Les\b|Une\b|Un\b|Si\b|"
        r"Pour\b|Dans\b|Ce\b|Cette\b|Tout\b|Toute\b|"
        r"Aucun\b|Aucune\b|Existe\b)",
        suite,
        flags=re.IGNORECASE,
    ):
        return suite

    return texte


def _suffixe_est_un_label_qcm(suite: str) -> bool:
    """Heuristique prudente pour reconnaitre un label A/B/C... colle au texte."""
    suite = suite.lstrip()
    if not suite:
        return False

    # Punctuation, nombres et tableau Markdown sont des debuts d'intitules,
    # pas des suites plausibles d'un identifiant matriciel comme AB = BA.
    if re.match(r"^(?:\||[+\-]?\d|[\[\]{}()<>])", suite):
        return True

    # Un mot francais naturel (ex. « Échange », « Toutes », « est »).
    if re.match(r"^[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]{1,}(?:\b|\s)", suite):
        return True

    # Une lettre seule suivie d'un mot français (ex. « C est », « A et B »).
    if re.match(r"^[A-ZÀ-ÖØ-Þ]\s+(?:est|et|sont|dans|pour|avec|ou|sur|par|du|de|des|la|le|les|une|un)\b", suite, flags=re.IGNORECASE):
        return True

    # Commandes TeX / groupes mathématiques structurés.
    if re.match(r"^(?:\\(?:begin|frac|sqrt|lambda)\b|\[|\()", suite):
        return True

    return False


def _normaliser_choix_liste(choix: list[Any]) -> list[str]:
    """Nettoie un ensemble de choix et retire les labels QCM concatenes."""
    textes = [normaliser_math_texte(c) for c in choix]
    labels = "ABCDEF"
    if not textes or len(textes) > len(labels):
        return textes

    prefixes = all(len(t) >= 2 and t[0] == labels[i] for i, t in enumerate(textes))
    if not prefixes:
        return [_normaliser_choix(t, i) for i, t in enumerate(textes)]

    # Les IA collent parfois le label au contenu : « AÉchange », « B2 »,
    # « C| ...tableau... » ou « AA+B... ». Lorsque le debut qui suit le label
    # ressemble clairement a une reponse (au moins une option), on retire
    # exactement un label de chaque choix de la serie.
    prefixe_obvie = any(
        len(t) >= 2 and t[:2] == labels[i] * 2
        or _suffixe_est_un_label_qcm(t[1:])
        for i, t in enumerate(textes)
    )
    if prefixe_obvie:
        return [normaliser_math_texte(t[1:]) for t in textes]

    return [_normaliser_choix(t, i) for i, t in enumerate(textes)]


def normaliser_choix_liste(choix: list[Any]) -> list[str]:
    """API publique pour nettoyer les choix avant rendu d'un quiz."""
    return _normaliser_choix_liste(choix)


def rendre_choix_math_html(choix: str, index: int):
    """Compatibilite : rend un choix individuel avec son index."""
    from markupsafe import Markup

    nettoye = _normaliser_choix(choix, index)
    return Markup(rendre_math_html(nettoye))


def valider_questions(questions: Any, expected_count: int | None = None, strict_coherence: bool = False) -> list[dict]:
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
        choix_nettoyes = _normaliser_choix_liste(choix)
        if strict_coherence:
            _verifier_coherence_explicative(
                choix_nettoyes,
                index,
                explication,
            )
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
