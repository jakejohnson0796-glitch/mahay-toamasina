"""Controle d'integrite du referentiel Toamasina versionne.

Le fichier source est organise par offre de formation : une meme filiere
peut donc apparaitre plusieurs fois lorsqu'elle est offerte a plusieurs
niveaux (ex. CCA M1 et CCA M2). Ces repetitions de niveau sont
intentionnelles et ne sont pas des doublons.

Le test bloque en revanche :
- deux lignes avec la meme identite academique
  (universite, composante, domaine, mention, niveau, parcours) ;
- deux variantes d'ecriture d'un meme domaine, mention ou parcours
  normalise ;
- des lignes strictement identiques.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "mahay_toamasina_referentiel_source.json"


def normaliser(valeur: object) -> str:
    texte = str(valeur or "").strip().replace("’", "'")
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texte).lower()


def charger_source() -> list[dict]:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    return payload["formations"]


def indexer(lignes: list[dict], champs: list[str]) -> dict[tuple[str, ...], list[int]]:
    index: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for numero, ligne in enumerate(lignes, start=1):
        cle = tuple(normaliser(ligne.get(champ)) for champ in champs)
        index[cle].append(numero)
    return index


def test_source_sans_doublon_academique() -> None:
    lignes = charger_source()
    champs = [
        "universite",
        "composante",
        "domaine",
        "mention",
        "niveau",
        "parcours",
    ]
    doublons = {
        cle: numeros
        for cle, numeros in indexer(lignes, champs).items()
        if len(numeros) > 1
    }
    assert not doublons, f"Doublons academiques detectes : {doublons}"


def test_source_sans_lignes_strictement_identiques() -> None:
    lignes = charger_source()
    champs = [
        "universite",
        "ville",
        "composante",
        "domaine",
        "mention",
        "niveau",
        "type",
        "parcours",
        "debut_specialisation",
        "fin_specialisation",
        "statut",
        "source",
    ]
    doublons = {
        cle: numeros
        for cle, numeros in indexer(lignes, champs).items()
        if len(numeros) > 1
    }
    assert not doublons, f"Lignes strictement dupliquees : {doublons}"


def test_source_sans_variantes_d_ecriture_cachees() -> None:
    lignes = charger_source()
    for champ in ("composante", "domaine", "mention", "type", "parcours", "source"):
        variantes: dict[str, set[str]] = defaultdict(set)
        for ligne in lignes:
            brut = str(ligne.get(champ) or "").strip()
            variantes[normaliser(brut)].add(brut)
        conflits = {
            cle: sorted(valeurs)
            for cle, valeurs in variantes.items()
            if cle and len(valeurs) > 1
        }
        assert not conflits, f"Variantes d'ecriture pour {champ}: {conflits}"


def test_repetitions_multi_niveaux_sont_permises_et_explicitement_attendues() -> None:
    lignes = charger_source()
    cca = [
        ligne
        for ligne in lignes
        if normaliser(ligne.get("mention")) == "gestion"
        and normaliser(ligne.get("parcours")) == "cca — comptabilite, controle, audit"
    ]
    assert {ligne["niveau"] for ligne in cca} == {"M1", "M2"}
