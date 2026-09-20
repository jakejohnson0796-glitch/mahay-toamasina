"""Recherche textuelle des Cercles.

La production utilise PostgreSQL lorsque disponible :
- dictionnaire français natif pour la morphologie ;
- unaccent pour ignorer les diacritiques ;
- recherche plein texte native et classement par pertinence.

SQLite (tests/dev) reçoit un fallback portable :
- normalisation Unicode accent/casse ;
- racines Snowball françaises ;
- recherche AND multi-termes.

Aucune normalisation n'est stockée dans les données métier : les libellés
affichés conservent donc toujours leur forme d'origine.
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import case
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import and_, or_, func

from .texte_normalise import normaliser

try:
    import snowballstemmer
except ImportError:  # pragma: no cover
    snowballstemmer = None

_CONFIG_POSTGRES = "french"
_MOTEUR_FRANCAIS = (
    snowballstemmer.stemmer("french")
    if snowballstemmer is not None
    else None
)

_STOP_WORDS_FR = {
    "a", "au", "aux", "avec", "ce", "ces", "dans", "de", "des", "du", "en",
    "et", "il", "la", "le", "les", "leur", "me", "mes", "mon", "ne", "nos",
    "notre", "nous", "on", "ou", "par", "pas", "pour", "que", "quel", "quelle",
    "quelles", "quels", "sa", "se", "ses", "son", "sur", "ta", "te", "tes",
    "ton", "tu", "un", "une", "vos", "votre", "vous", "y",
}


def termes_recherche(texte: str | None) -> list[str]:
    """Nettoie une requête, retire les mots vides et borne sa taille."""
    brut = " ".join((texte or "").split())[:160]
    termes: list[str] = []
    for token in brut.split():
        token_normalise = normaliser(token).strip(".,;:!?()[]{}<>\"'-_/\\")
        if not token_normalise or token_normalise in _STOP_WORDS_FR:
            continue
        if len(token_normalise) < 2:
            continue
        if token_normalise not in termes:
            termes.append(token_normalise)
    return termes[:8]


def racines_francaises(terme: str) -> list[str]:
    """Retourne le terme normalisé et sa racine Snowball, sans doublon."""
    valeurs = [normaliser(terme)]
    if _MOTEUR_FRANCAIS is not None:
        try:
            racine = normaliser(_MOTEUR_FRANCAIS.stemWord(terme))
            if racine and racine not in valeurs and len(racine) >= 3:
                valeurs.append(racine)
        except Exception:
            pass
    return valeurs


def _texte_pondere_postgres(colonnes: Iterable[ColumnElement]) -> ColumnElement:
    """Construit un tsvector pondéré : titre > référentiel > description."""
    nom, referentiel, description = list(colonnes)
    return (
        func.setweight(
            func.to_tsvector(_CONFIG_POSTGRES, func.unaccent(func.coalesce(nom, ""))), "A"
        )
        .op("||")(
            func.setweight(
                func.to_tsvector(_CONFIG_POSTGRES, func.unaccent(func.coalesce(referentiel, ""))),
                "B",
            )
        )
        .op("||")(
            func.setweight(
                func.to_tsvector(_CONFIG_POSTGRES, func.unaccent(func.coalesce(description, ""))),
                "D",
            )
        )
    )


def clause_recherche_cercles(
    session,
    query: str | None,
    nom: ColumnElement,
    description: ColumnElement,
    referentiel: ColumnElement,
) -> tuple[ColumnElement | None, ColumnElement | None]:
    """Renvoie (condition, score) pour une recherche de Cercles."""
    brut = " ".join((query or "").split())[:160]
    termes = termes_recherche(brut)
    if not termes:
        return None, None

    dialecte = session.get_bind().dialect.name
    if dialecte == "postgresql":
        document = _texte_pondere_postgres([nom, referentiel, description])
        tsquery = func.websearch_to_tsquery(
            _CONFIG_POSTGRES,
            func.unaccent(brut),
        )
        return document.op("@@")(tsquery), func.ts_rank_cd(document, tsquery, 32)

    champs = [nom, referentiel, description]
    conditions = []
    score = 0
    for terme in termes:
        conditions_terme = []
        for variante in racines_francaises(terme):
            motif = f"%{variante}%"
            conditions_terme.extend(
                func.mahay_normaliser(champ).like(motif) for champ in champs
            )
            score += case(
                (func.mahay_normaliser(nom).like(f"{variante}%"), 100),
                (func.mahay_normaliser(referentiel).like(f"{variante}%"), 60),
                (func.mahay_normaliser(description).like(f"%{variante}%"), 10),
                else_=0,
            )
        conditions.append(or_(*conditions_terme))

    return and_(*conditions), score
