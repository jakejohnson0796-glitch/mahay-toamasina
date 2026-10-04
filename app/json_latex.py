r"""Lecture robuste du JSON produit par les modèles IA quand le contenu contient du LaTeX.

Le modèle peut parfois produire "\\frac" correctement échappé ou, plus rarement,
un JSON apparent contenant "\frac" directement. Le second cas est invalide/ambigu
pour le parseur JSON car certaines séquences comme "\f" ou "\n" ont une signification
JSON. Ce module répare uniquement les antislashs qui ressemblent à des commandes
LaTeX avant d'appeler json.loads().

Important :
- cette fonction ne normalise pas le texte métier ;
- elle ne remplace pas les formules ;
- elle ne doit être utilisée que pour lire une sortie JSON venant du modèle ;
- la lecture des JSON stockés en base continue d'utiliser json.loads() normalement.
"""

from __future__ import annotations

import json
import re
from typing import Any


_COMMAND_RE = re.compile(r"[A-Za-z]+")


def _reparer_antislashs_latex(texte: str) -> str:
    """Répare les commandes LaTeX non échappées à l'intérieur de chaînes JSON."""
    sortie: list[str] = []
    dans_chaine = False
    i = 0
    longueur = len(texte)

    while i < longueur:
        caractere = texte[i]

        if caractere == '"':
            # Une quote échappée appartient au contenu de la chaîne.
            if dans_chaine and i > 0:
                nb_antislashs = 0
                j = i - 1
                while j >= 0 and texte[j] == '\\':
                    nb_antislashs += 1
                    j -= 1
                if nb_antislashs % 2 == 1:
                    sortie.append(caractere)
                    i += 1
                    continue

            dans_chaine = not dans_chaine
            sortie.append(caractere)
            i += 1
            continue

        if not dans_chaine or caractere != '\\':
            sortie.append(caractere)
            i += 1
            continue

        # MODIF : une double barre oblique est déjà correctement échappée
        # dans le JSON ; on la conserve telle quelle.
        if i + 1 < longueur and texte[i + 1] == '\\':
            sortie.extend(["\\", "\\"])
            i += 2
            continue

        suivant = texte[i + 1] if i + 1 < longueur else ""

        # MODIF : les commandes LaTeX sont reconnues avant les échappements
        # JSON usuels. Ainsi \frac, \mathbb, \begin, \ce, \mathrm, \nu...
        # deviennent \\frac, \\mathbb, etc. dans le JSON source, puis
        # json.loads() restitue une seule barre dans la donnée métier.
        # MODIF : \uXXXX est un escape JSON valide et doit être conservé
        # avant de tester les commandes LaTeX alphabétiques.
        if suivant == "u" and i + 6 < longueur:
            quatre = texte[i + 2:i + 6]
            if re.fullmatch(r"[0-9A-Fa-f]{4}", quatre):
                sortie.extend(["\\", "u", quatre])
                i += 6
                continue

        if suivant.isalpha():
            match = _COMMAND_RE.match(texte, i + 1)
            mot = match.group(0) if match else ""
            if len(mot) > 1:
                sortie.extend(["\\", "\\", mot])
                i += 1 + len(mot)
                continue

        # MODIF : les délimiteurs/formats LaTeX qui ne sont pas des commandes
        # alphabétiques sont aussi protégés.
        if suivant in "[](){}_^,;:!%&":
            sortie.extend(["\\", "\\", suivant])
            i += 2
            continue

        # MODIF : les séquences JSON valides simples (\", \\, \/, \b,
        # \f, \n, \r, \t) restent des escapes JSON. Le cas \f... a déjà
        # été capturé comme commande LaTeX ci-dessus lorsqu'il forme \frac,
        # \forall, etc.
        if suivant in '"\\/bfnrt':
            sortie.extend(["\\", suivant])
            i += 2
            continue

        # MODIF : un escape inconnu est traité comme une barre LaTeX littérale.
        sortie.extend(["\\", "\\", suivant] if suivant else ["\\", "\\"])
        i += 2 if suivant else 1

    return "".join(sortie)


def charger_json_ia(texte_brut: str | bytes | bytearray | Any) -> Any:
    """Charge un JSON provenant d'un modèle sans perdre ses antislashs LaTeX."""
    if isinstance(texte_brut, (dict, list, int, float, bool)) or texte_brut is None:
        # MODIF : les sorties déjà décodées sont retournées sans transformation.
        return texte_brut

    if isinstance(texte_brut, (bytes, bytearray)):
        texte = bytes(texte_brut).decode("utf-8")
    else:
        texte = str(texte_brut)

    # MODIF : on répare d'abord les commandes LaTeX ambiguës, puis on lit le
    # JSON. Cela évite qu'un \frac soit interprété par json.loads() comme
    # l'escape JSON \f avant que nous ayons pu le préserver.
    repare = _reparer_antislashs_latex(texte)
    try:
        return json.loads(repare)
    except json.JSONDecodeError as erreur_repare:
        # MODIF : repli strict sur la lecture directe pour les JSON non concernés
        # par le problème LaTeX ; aucune donnée métier n'est normalisée.
        try:
            return json.loads(texte)
        except json.JSONDecodeError:
            raise erreur_repare
