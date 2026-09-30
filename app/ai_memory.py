"""Memoire persistante de l'ensemble IA.

La memoire enregistre des signaux d'erreur recurrente sous forme compacte :
categorie + empreinte + compteur. Elle est ensuite injectee dans les
prompts futurs comme garde-fou, sans conserver le texte brut de la critique.
"""
import hashlib
import re
from datetime import datetime
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from .database import engine
from .models import ErreurIAEnsemble


_CATEGORIES = (
    ("ambiguite", ("ambigu", "plusieurs bonne", "plusieurs reponse")),
    ("choix_reponse", ("choix", "distracteur", "bonne reponse", "reponse correcte", "index")),
    ("explication", ("explication", "justification")),
    ("correction", ("correction", "exercice", "solution")),
    ("mathematique", ("calcul", "math", "equation", "arithmet", "formule")),
    ("coherence", ("coherent", "coherence", "contradiction", "contradic")),
    ("langue", ("grammaire", "orthograph", "syntaxe", "accord")),
    ("pedagogie", ("pedagog", "niveau", "etudiant")),
)


def normaliser_probleme(probleme: Any) -> str:
    texte = " ".join(str(probleme or "").split()).strip().lower()
    return texte[:1000]


def categorie_probleme(probleme: Any) -> str:
    texte = normaliser_probleme(probleme)
    if not texte:
        return "inconnu"
    for categorie, mots in _CATEGORIES:
        if any(mot in texte for mot in mots):
            return categorie
    return "contenu"


def signature_probleme(probleme: Any) -> str:
    texte = normaliser_probleme(probleme)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:16]


def enregistrer_audit_ensemble(
    audit: Dict[str, Any],
    *,
    type_interaction: str,
    matiere: Optional[str] = None,
    niveau: Optional[str] = None,
) -> int:
    """Persiste les signaux d'erreur des critiques et retourne leur nombre."""
    maintenant = datetime.utcnow()
    total = 0
    matiere_norm = (matiere or "").strip()
    niveau_norm = (niveau or "").strip()

    try:
        with Session(engine) as session:
            for item in audit.get("critics") or []:
                modele = str(item.get("model") or "inconnu")
                avis = item.get("avis") or {}
                for probleme in avis.get("problemes") or []:
                    probleme_norm = normaliser_probleme(probleme)
                    if not probleme_norm:
                        continue
                    total += 1
                    categorie = categorie_probleme(probleme_norm)
                    signature = signature_probleme(probleme_norm)
                    existant = session.exec(
                        select(ErreurIAEnsemble).where(
                            ErreurIAEnsemble.type_interaction == type_interaction,
                            ErreurIAEnsemble.matiere == matiere_norm,
                            ErreurIAEnsemble.niveau == niveau_norm,
                            ErreurIAEnsemble.modele == modele,
                            ErreurIAEnsemble.categorie == categorie,
                            ErreurIAEnsemble.signature == signature,
                        )
                    ).first()
                    if existant:
                        existant.occurrences += 1
                        existant.derniere_detection_le = maintenant
                        session.add(existant)
                    else:
                        session.add(
                            ErreurIAEnsemble(
                                type_interaction=type_interaction,
                                matiere=matiere_norm,
                                niveau=niveau_norm,
                                modele=modele,
                                categorie=categorie,
                                signature=signature,
                                occurrences=1,
                                premiere_detection_le=maintenant,
                                derniere_detection_le=maintenant,
                            )
                        )
            session.commit()
    except Exception:
        # La memoire est un bonus : aucune panne DB de telemetry ne doit
        # bloquer la generation ou la correction d'un quiz/tuteur.
        return 0

    return total


def nb_signaux_recurrents(
    *,
    type_interaction: str,
    matiere: Optional[str] = None,
    niveau: Optional[str] = None,
) -> int:
    """Retourne le volume cumule de signaux memorises pour un contexte."""
    try:
        with Session(engine) as session:
            elements = session.exec(
                select(ErreurIAEnsemble).where(
                    ErreurIAEnsemble.type_interaction == type_interaction,
                    ErreurIAEnsemble.matiere == (matiere or "").strip(),
                    ErreurIAEnsemble.niveau == (niveau or "").strip(),
                )
            ).all()
            return sum(max(0, int(x.occurrences)) for x in elements)
    except Exception:
        return 0


def contexte_erreurs_recurrentes(
    *,
    type_interaction: str,
    matiere: Optional[str] = None,
    niveau: Optional[str] = None,
    limit: int = 6,
) -> str:
    """Retourne un garde-fou court base sur les erreurs deja observees."""
    matiere_norm = (matiere or "").strip()
    niveau_norm = (niveau or "").strip()
    try:
        with Session(engine) as session:
            elements = session.exec(
                select(ErreurIAEnsemble)
                .where(
                    ErreurIAEnsemble.type_interaction == type_interaction,
                    ErreurIAEnsemble.matiere == matiere_norm,
                    ErreurIAEnsemble.niveau == niveau_norm,
                )
                .order_by(
                    ErreurIAEnsemble.occurrences.desc(),
                    ErreurIAEnsemble.derniere_detection_le.desc(),
                )
                .limit(limit)
            ).all()
    except Exception:
        return ""

    if not elements:
        return ""

    lignes = []
    vus = set()
    for element in elements:
        cle = (element.categorie, element.modele)
        if cle in vus:
            continue
        vus.add(cle)
        lignes.append(
            f"- {element.categorie}: signal recurrent ({element.occurrences} occurrence(s), "
            f"modele={element.modele})"
        )

    if not lignes:
        return ""

    return (
        "MEMOIRE DE L'ENSEMBLE — points a verifier en priorite, issus des "
        "interactions precedentes. Cette memoire est un garde-fou, pas une "
        "verite : confirme toujours l'erreur avant de corriger.\n"
        + "\n".join(lignes)
    )
