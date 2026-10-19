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
from math import gcd
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
- INTERDICTION DES BACKTICKS POUR LES MATHS : n'entoure jamais une formule, une fraction, une égalité, un calcul ou une puissance avec des backticks Markdown. Les backticks sont réservés au code informatique réel. Même dans une liste, écris toute l'identité dans un seul délimiteur LaTeX, par exemple \\(123456=156\\\\times789+372\\), et jamais seulement la partie gauche en code avec l'opérateur en texte à côté.
- FRACTIONS : écris toujours le numérateur et le dénominateur explicitement avec \\(\\\\frac{a}{b}\\) ou \\[\\\\frac{a}{b}\\]. N'écris jamais les deux nombres collés, ni seulement la fraction visuelle sans commandes LaTeX. Pour \\(\\\\frac{123456000}{789000}\\), conserve explicitement les deux nombres dans le numérateur et le dénominateur.
- RÉDUCTION DE FRACTION PAR PGCD : chaque étape reste une fraction explicite, jamais des chiffres accolés ni une suite de barres obliques ambiguë. Écris par exemple \\(\\frac{9876543210}{1234560}=\\frac{987654321}{123456}=\\frac{329218107}{41152}\\). Avant d’afficher le résultat final, vérifie séparément le numérateur et le dénominateur après division par le PGCD.
- PUISSANCES : écris chaque exposant explicitement, par exemple \\(10^{3}\\), jamais le nombre 103 collé pour représenter dix puissance trois. N'aplatis jamais les indices/exposants en nombres ordinaires.
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


def _corriger_chaine_euclide(source: str) -> str:
    """Reconstruit une suite continue de divisions d'Euclide à partir de ses deux premiers nombres."""
    lignes = source.splitlines(keepends=True)
    sortie: list[str] = []
    index = 0

    def extraire(ligne: str):
        contenu = ligne.rstrip("\r\n")
        candidat = contenu.replace(chr(96), "")
        match = _MOTIF_IDENTITE_EUCLIDE.search(candidat)
        return candidat, match

    while index < len(lignes):
        candidat, match = extraire(lignes[index])
        if not match:
            sortie.append(lignes[index])
            index += 1
            continue

        bloc = [(lignes[index], candidat, match)]
        suivant = index + 1
        while suivant < len(lignes):
            candidat_suivant, match_suivant = extraire(lignes[suivant])
            if not match_suivant:
                break
            bloc.append((lignes[suivant], candidat_suivant, match_suivant))
            suivant += 1

        if len(bloc) < 2 or int(bloc[1][2].group("dividende")) != int(match.group("diviseur")):
            sortie.append(lignes[index])
            index += 1
            continue

        a = int(match.group("dividende"))
        b = int(match.group("diviseur"))
        if a < 0 or b <= 0:
            sortie.extend(ligne for ligne, _, _ in bloc)
            index = suivant
            continue

        prefixes = [candidat_ligne[:match_ligne.start()] for _, candidat_ligne, match_ligne in bloc]
        prefix_numero = re.match(r"^(\s*)(\d+)([.)]\s*)$", prefixes[0])
        formules: list[tuple[int, int, int, int]] = []
        while b:
            quotient, reste = divmod(a, b)
            formules.append((a, quotient, b, reste))
            a, b = b, reste

        nouveaux: list[str] = []
        for position, (a, quotient, b, reste) in enumerate(formules):
            if prefix_numero:
                prefixe = f"{prefix_numero.group(1)}{int(prefix_numero.group(2)) + position}{prefix_numero.group(3)}"
            elif position < len(prefixes):
                prefixe = prefixes[position]
            else:
                prefixe = prefixes[0]
            nouveaux.append(prefixe + rf"\({a}={quotient}\times{b}+{reste}\)")

        derniere_ligne = lignes[suivant - 1]
        fin_ligne_match = re.search(r"(\r\n|\n|\r)$", derniere_ligne)
        fin_ligne = fin_ligne_match.group(1) if fin_ligne_match else ""
        derniere_texte = derniere_ligne.rstrip("\r\n").rstrip()
        ponctuation = derniere_texte[-1] if derniere_texte and derniere_texte[-1] in ".!?;:" else ""
        if ponctuation:
            nouveaux[-1] += ponctuation

        sortie.extend(ligne + ("\n" if position < len(nouveaux) - 1 else fin_ligne)
                      for position, ligne in enumerate(nouveaux))
        index = suivant

    return "".join(sortie)


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

    source = _corriger_chaine_euclide(source)

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
        suffixe = candidate[match.end():]
        suffixe_normalise = re.sub(r"\\(?:times|cdot|div)(?![A-Za-z])", "×", suffixe)
        suffixe_normalise = re.sub(r"\t?imes(?![A-Za-z])", "×", suffixe_normalise)
        ponctuation_finale = re.search(r"[.!?;:]\s*$", suffixe_normalise)
        suffixe_calcul = (
            suffixe_normalise[:ponctuation_finale.start()]
            if ponctuation_finale
            else suffixe_normalise
        )
        suffixe_est_expansion = bool(
            suffixe_calcul.strip()
            and "=" in suffixe_calcul
            and re.search(r"[-−]\s*\d", suffixe_calcul)
            and re.search(r"[×x]\s*\d", suffixe_calcul)
            and re.fullmatch(r"[\d\s,.\-+−*/×÷=()]+", suffixe_calcul.strip())
        )

        operator_corrompu = "\t" in contenu_ligne or chr(96) in contenu_ligne
        if (
            quotient_correct == quotient_recu
            and reste_correct == reste_recu
            and not operator_corrompu
            and not suffixe_est_expansion
        ):
            resultat.append(ligne)
            continue

        formule = (
            rf"\({dividende}={quotient_correct}\times{diviseur}+{reste_correct}\)"
        )
        if suffixe_est_expansion:
            ponctuation = ponctuation_finale.group(0) if ponctuation_finale else ""
            candidate = candidate[:match.start()] + formule + ponctuation
        else:
            candidate = candidate[:match.start()] + formule + candidate[match.end():]
        resultat.append(candidate + fin_ligne)

    return "".join(resultat)


_CONTEXTE_FRACTION_PGCD = re.compile(
    r"\b(?:pgcd|euclide)\b|réduction\s+de\s+fraction|fraction\s+(?:irréductible|réduite)",
    re.IGNORECASE,
)
_MOTIF_REDUCTION_DIX = re.compile(
    r"(?P<original>\d{3,})\s*=\s*(?P<reduit>\d{2,})\s*(?:\\times|×|x|\*)\s*10\b",
    re.IGNORECASE,
)


def corriger_fraction_pgcd_mal_formatee(
    texte: Any, *, contexte_pgcd: bool = False
) -> str:
    """Répare les fractions concaténées si deux réductions par 10
    identifient sans ambiguïté le numérateur et le dénominateur.
    """
    source = convertir_math_transport_texte(texte)
    if not (contexte_pgcd or _CONTEXTE_FRACTION_PGCD.search(source)):
        return source

    reductions = []
    for match in _MOTIF_REDUCTION_DIX.finditer(source):
        original = int(match.group("original"))
        reduit = int(match.group("reduit"))
        if original == reduit * 10:
            reductions.append(match.group("reduit"))

    if len(reductions) < 2:
        return source

    numerateur = int(reductions[0])
    denominateur = int(reductions[1])
    if numerateur <= 0 or denominateur <= 0:
        return source

    diviseur_commun = gcd(numerateur, denominateur)
    if diviseur_commun <= 0:
        return source
    numerateur_reduit = numerateur // diviseur_commun
    denominateur_reduit = denominateur // diviseur_commun

    numerateur_texte = str(numerateur)
    denominateur_texte = str(denominateur)
    numerateur_final_texte = str(numerateur_reduit)
    denominateur_final_texte = str(denominateur_reduit)
    fraction_initiale = rf"\(\frac{{{numerateur}}}{{{denominateur}}}\)"
    fraction_finale = rf"\(\frac{{{numerateur_reduit}}}{{{denominateur_reduit}}}\)"
    fraction_complete = (
        rf"\(\frac{{{numerateur}}}{{{denominateur}}}"
        rf"=\frac{{{numerateur_reduit}}}{{{denominateur_reduit}}}\)"
    )

    joint_initial = numerateur_texte + denominateur_texte
    joint_final = numerateur_final_texte + denominateur_final_texte

    # Cas fréquent : la barre de fraction a disparu entre les deux entiers.
    motif_reste = re.compile(
        rf"(?i)(il\s+reste\s+)(?:\x60)?{re.escape(joint_initial)}(?:\x60)?"
    )
    source = motif_reste.sub(lambda m: m.group(1) + fraction_initiale, source)

    lignes = source.splitlines(keepends=True)
    corrigees: list[str] = []
    sauter_expression_suivante = False
    for ligne in lignes:
        if sauter_expression_suivante:
            if not ligne.strip():
                corrigees.append(ligne)
                continue
            sauter_expression_suivante = False
            ligne_sans_code = ligne.replace(chr(96), "")
            if (
                (joint_initial in ligne_sans_code or joint_final in ligne_sans_code)
                and ("/" in ligne_sans_code or "=" in ligne_sans_code)
                and not _CONTEXTE_FRACTION_PGCD.search(ligne_sans_code)
            ):
                continue

        entete = re.match(
            r"^(?P<prefixe>[ \t]*(?:\d+[.)]\s*)?Division\s+par\s+le\s+PGCD\s*:)"
            r"(?P<reste>.*?)(?P<fin>\r?\n)?$",
            ligne,
            re.IGNORECASE,
        )
        if entete:
            contenu_entete = entete.group("reste") or ""
            fin_ligne = entete.group("fin") or ""
            if (
                r"\frac{" + numerateur_texte + r"}{" + denominateur_texte + "}"
                in contenu_entete
            ):
                corrigees.append(ligne)
            else:
                corrigees.append(
                    entete.group("prefixe") + " " + fraction_complete + fin_ligne
                )
                sauter_expression_suivente = True
            continue

        motif_final = re.compile(
            rf"(?i)(fraction\s+finale\s+r[ée]duite\s+est\s+)(?:\x60)?"
            rf"{re.escape(joint_final)}(?:\x60)?"
        )
        ligne = motif_final.sub(lambda m: m.group(1) + fraction_finale, ligne)
        corrigees.append(ligne)

    resultat = "".join(corrigees)
    # Garde-fou final : si une ancienne ligne de calcul a échappé au saut de
    # ligne précédent, ne jamais laisser l'expression "a/b/...=numden" brute.
    lignes_nettoyees = []
    for ligne in resultat.splitlines(keepends=True):
        ligne_sans_code = ligne.replace(chr(96), "")
        if (
            joint_final in ligne_sans_code
            and "/" in ligne_sans_code
            and "=" in ligne_sans_code
            and not re.search(r"(?i)fraction\s+finale\s+r[ée]duite\s+est", ligne_sans_code)
        ):
            continue
        lignes_nettoyees.append(ligne)
    resultat = "".join(lignes_nettoyees)
    resultat = re.sub(
        rf"\x60{re.escape(joint_final)}\x60",
        lambda _m: fraction_finale,
        resultat,
    )
    return resultat


_MOTIF_PGCD_DE = re.compile(
    r"\bPGCD\s+de\s+(?P<numerateur>\d{1,18})\s+et\s+(?P<denominateur>\d{1,18})\b",
    re.IGNORECASE,
)
_MOTIF_PGCD_PARENTHESES = re.compile(
    r"\bPGCD\s*\(\s*(?P<numerateur>\d{1,18})\s*[,;]\s*(?P<denominateur>\d{1,18})\s*\)",
    re.IGNORECASE,
)


def _extraire_paires_pgcd(texte: str) -> list[tuple[int, int]]:
    occurrences: list[tuple[int, tuple[int, int]]] = []
    for motif in (_MOTIF_PGCD_DE, _MOTIF_PGCD_PARENTHESES):
        for match in motif.finditer(texte or ""):
            numerateur = int(match.group("numerateur"))
            denominateur = int(match.group("denominateur"))
            if numerateur > 0 and denominateur > 0 and numerateur != denominateur:
                occurrences.append((match.start(), (numerateur, denominateur)))
    paires: list[tuple[int, int]] = []
    for _, paire in sorted(occurrences, key=lambda item: item[0]):
        if paire not in paires:
            paires.append(paire)
    return paires


def _chaine_euclide_pour_fraction(
    numerateur: int, denominateur: int
) -> list[tuple[int, int, int, int]]:
    """Construit la chaîne d'Euclide correcte à partir des deux termes."""
    a, b = max(numerateur, denominateur), min(numerateur, denominateur)
    chaine: list[tuple[int, int, int, int]] = []
    while b:
        quotient, reste = divmod(a, b)
        chaine.append((a, quotient, b, reste))
        a, b = b, reste
    return chaine


def corriger_pgcd_selon_paires(
    texte: Any, *, paires_contextuelles: list[tuple[int, int]] | None = None
) -> str:
    """Rattache fraction, chaîne d'Euclide, PGCD et résultat final à la même paire."""
    source = convertir_math_transport_texte(texte)
    if not _CONTEXTE_FRACTION_PGCD.search(source) and not paires_contextuelles:
        return source

    references_locales = _extraire_paires_pgcd(source)
    candidates: list[tuple[int, int]] = []
    for paire in references_locales + (paires_contextuelles or []):
        if paire not in candidates and paire[0] > 0 and paire[1] > 0:
            candidates.append(paire)
    if not candidates:
        return source

    def contient_nombre(nombre: int, valeur: str) -> bool:
        return bool(re.search(rf"(?<!\d){nombre}(?!\d)", valeur))

    def groupes_formules(valeur: str) -> list[list[re.Match[str]]]:
        groupes: list[list[re.Match[str]]] = []
        for match in _MOTIF_IDENTITE_EUCLIDE.finditer(valeur):
            if groupes:
                precedent = groupes[-1][-1]
                intervalle = valeur[precedent.end():match.start()]
                nettoye = re.sub(r"[\s,;:—\-•\x60\()]+", "", intervalle)
                if not nettoye and len(intervalle) <= 64:
                    groupes[-1].append(match)
                    continue
            groupes.append([match])
        return groupes

    groupes = groupes_formules(source)
    paires_actives: list[tuple[int, int]] = []
    for numerateur, denominateur in candidates:
        pgcd = gcd(numerateur, denominateur)
        if pgcd <= 0:
            continue
        joint_initial = f"{numerateur}{denominateur}"
        joint_final = f"{numerateur // pgcd}{denominateur // pgcd}"
        token_initial = bool(re.search(rf"\x60{re.escape(joint_initial)}\x60", source))
        division_collee = bool(re.search(
            rf"\x60?{numerateur}\s*(?:÷|\\\\div|/)\s*{pgcd}"
            rf"\s*{denominateur}\s*(?:÷|\\\\div|/)\s*{pgcd}"
            rf"\s*=\s*{re.escape(joint_final)}\x60?",
            source,
        ))
        resultat_colle = bool(re.search(
            rf"(?i)(?:fraction|résultat|irréductible|réduite)[^\n]{{0,100}}"
            rf"\x60?{re.escape(joint_final)}\x60?",
            source,
        ))
        reference_locale = (numerateur, denominateur) in references_locales
        groupe_correspondant = any(
            contient_nombre(numerateur, source[g[0].start():g[-1].end()])
            and contient_nombre(denominateur, source[g[0].start():g[-1].end()])
            for g in groupes
        )
        termes_present = contient_nombre(numerateur, source) and contient_nombre(denominateur, source)
        fraction_seule = len(candidates) == 1 and bool(re.search(
            r"(?i)fraction|irréductible|réduite", source
        ))
        if token_initial or division_collee or resultat_colle or reference_locale or groupe_correspondant or (
            termes_present and len(candidates) == 1
        ) or fraction_seule:
            paires_actives.append((numerateur, denominateur))

    if not paires_actives:
        return source

    for numerateur, denominateur in paires_actives:
        pgcd = gcd(numerateur, denominateur)
        nr, dr = numerateur // pgcd, denominateur // pgcd
        joint_initial, joint_final = f"{numerateur}{denominateur}", f"{nr}{dr}"
        fraction_initiale = rf"\(\frac{{{numerateur}}}{{{denominateur}}}\)"
        fraction_finale = rf"\(\frac{{{nr}}}{{{dr}}}\)"

        # Les chiffres accolés ne sont réparés que si la paire a été identifiée.
        # Retrouve aussi le cas où le transport a déjà supprimé les backticks.
        source = re.sub(
            rf"(?<!\d){re.escape(joint_initial)}(?!\d)",
            lambda _m, formule=fraction_initiale: formule,
            source,
        )

        # Exemple : 48÷12180÷12=415 devient 48÷12=4 et 180÷12=15.
        motif_divisions = re.compile(
            rf"(?i)\x60?{numerateur}\s*(?:÷|\\div|/)\s*{pgcd}"
            rf"\s*{denominateur}\s*(?:÷|\\div|/)\s*{pgcd}"
            rf"\s*=\s*{joint_final}\x60?"
        )
        divisions_correctes = (
            rf"\({numerateur}\div{pgcd}={nr}\)"
            rf" et \({denominateur}\div{pgcd}={dr}\)"
        )
        source = motif_divisions.sub(lambda _match, formule=divisions_correctes: formule, source)

        # Le résultat final utilise une fraction, jamais les deux termes collés.
        source = re.sub(
            rf"(?i)(fraction\s+(?:(?:finale|réduite|irréductible)\s+)?"
            rf"(?:est(?:\s+maintenant)?|:)\s*)\x60?{re.escape(joint_final)}\x60?",
            lambda m, formule=fraction_finale: m.group(1) + formule,
            source,
        )

    # Réassocie chaque groupe d'identités à la paire dont il contient les deux termes.
    groupes = groupes_formules(source)
    remplacements: list[tuple[int, int, str]] = []
    for groupe in groupes:
        debut, fin = groupe[0].start(), groupe[-1].end()
        bloc = source[debut:fin]
        possibles = []
        for numerateur, denominateur in paires_actives:
            n_present = contient_nombre(numerateur, bloc)
            d_present = contient_nombre(denominateur, bloc)
            voisinage = source[max(0, debut - 220):min(len(source), fin + 220)]
            reference_voisine = (numerateur, denominateur) in _extraire_paires_pgcd(voisinage)
            score = int(n_present) + int(d_present)
            if score == 2 or reference_voisine:
                possibles.append((score * 10 + int(reference_voisine), numerateur, denominateur))
        if not possibles:
            continue
        meilleur_score = max(item[0] for item in possibles)
        meilleurs = {(item[1], item[2]) for item in possibles if item[0] == meilleur_score}
        if len(meilleurs) != 1:
            continue

        numerateur, denominateur = next(iter(meilleurs))
        chaines = _chaine_euclide_pour_fraction(numerateur, denominateur)
        textes_formules = [
            rf"\({a}={quotient}\times{b}+{reste}\)"
            for a, quotient, b, reste in chaines
        ]
        debut_remplacement = debut
        if source[max(0, debut - 2):debut] == r"\(":
            debut_remplacement -= 2
        elif debut > 0 and source[debut - 1] == chr(96):
            debut_remplacement -= 1
        fin_remplacement = fin
        if source[fin_remplacement:fin_remplacement + 2] == r"\)":
            fin_remplacement += 2
        while fin_remplacement < len(source) and source[fin_remplacement] in (chr(96), ")"):
            fin_remplacement += 1
        remplacements.append((debut_remplacement, fin_remplacement, ", ".join(textes_formules)))

    for debut, fin, remplacement in reversed(remplacements):
        source = source[:debut] + remplacement + source[fin:]

    # Ajoute le résultat à la phrase pédagogique la plus proche de sa référence PGCD.
    phrase = re.compile(
        r"(?i)(la\s+fraction\s+est\s+maintenant\s+irréductible)(?!\s*[:;])"
    )
    decalage = 0
    for mention in list(phrase.finditer(source)):
        position = mention.start() + decalage
        refs = _extraire_paires_pgcd(source[max(0, position - 240):position])
        paire = refs[-1] if refs else (paires_actives[0] if len(paires_actives) == 1 else None)
        if not paire or paire not in paires_actives:
            continue
        pgcd = gcd(paire[0], paire[1])
        formule = rf"\(\frac{{{paire[0] // pgcd}}}{{{paire[1] // pgcd}}}\)"
        ajout = mention.group(1) + " : " + formule
        debut, fin = mention.start() + decalage, mention.end() + decalage
        source = source[:debut] + ajout + source[fin:]
        decalage += len(ajout) - (fin - debut)

    return source


def normaliser_structure_quiz(questions: list[Mapping[str, Any]] | None) -> list[dict]:
    """Préserve les champs du quiz et corrige uniquement les divisions euclidiennes identifiables."""
    resultat: list[dict] = []
    for question in questions or []:
        item = dict(question)
        question_brute = convertir_math_transport_texte(item.get("question", ""))
        explication_brute = convertir_math_transport_texte(item.get("explication", ""))
        choix_bruts = [
            convertir_math_transport_texte(choix)
            for choix in (item.get("choix") or [])
        ]
        texte_global = " ".join([question_brute, explication_brute, *choix_bruts])
        contexte_euclide = _contexte_euclide_present(
            question_brute, explication_brute, *choix_bruts
        )
        contexte_pgcd = bool(_CONTEXTE_FRACTION_PGCD.search(texte_global))
        paires_contextuelles = _extraire_paires_pgcd(texte_global)
        item["question"] = corriger_pgcd_selon_paires(
            corriger_fraction_pgcd_mal_formatee(
                corriger_identites_euclide(
                    question_brute, contexte_euclide=contexte_euclide
                ),
                contexte_pgcd=contexte_pgcd,
            ),
            paires_contextuelles=paires_contextuelles,
        )
        item["choix"] = [
            corriger_pgcd_selon_paires(
                corriger_fraction_pgcd_mal_formatee(
                    corriger_identites_euclide(
                        choix, contexte_euclide=contexte_euclide
                    ),
                    contexte_pgcd=contexte_pgcd,
                ),
                paires_contextuelles=paires_contextuelles,
            )
            for choix in choix_bruts
        ]
        item["explication"] = corriger_pgcd_selon_paires(
            corriger_fraction_pgcd_mal_formatee(
                corriger_identites_euclide(
                    explication_brute, contexte_euclide=contexte_euclide
                ),
                contexte_pgcd=contexte_pgcd,
            ),
            paires_contextuelles=paires_contextuelles,
        )
        resultat.append(item)
    return resultat


def normaliser_structure_tuteur(
    reponse: Mapping[str, Any] | None,
) -> dict[str, str]:
    """Préserve les quatre sections, en corrigeant les divisions euclidiennes ciblées si besoin."""
    source = reponse or {}
    sections = {
        "explication": convertir_math_transport_texte(source.get("explication", "")),
        "exemple": convertir_math_transport_texte(source.get("exemple", "")),
        "exercice": convertir_math_transport_texte(source.get("exercice", "")),
        "correction": convertir_math_transport_texte(source.get("correction", "")),
    }
    texte_global = "\n".join(sections.values())
    contexte_euclide = _contexte_euclide_present(*sections.values())
    contexte_pgcd = bool(_CONTEXTE_FRACTION_PGCD.search(texte_global))
    paires_contextuelles = _extraire_paires_pgcd(texte_global)
    return {
        cle: corriger_pgcd_selon_paires(
            corriger_fraction_pgcd_mal_formatee(
                corriger_identites_euclide(
                    valeur, contexte_euclide=contexte_euclide
                ),
                contexte_pgcd=contexte_pgcd,
            ),
            paires_contextuelles=paires_contextuelles,
        )
        for cle, valeur in sections.items()
    }
