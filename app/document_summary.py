"""Fiche pédagogique des documents : résumé, objectifs et notions utiles aux étudiants.

Les résumés IA ne participent jamais à la modération du document. En cas
d'absence de clé IA, d'extraction impossible ou de réponse non exploitable,
un aperçu provisoire explicite est enregistré plutôt que d'inventer le cours.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from groq import Groq
from sqlmodel import Session

from .config import parametres
from .database import engine
from .models import Document, Filiere
from .storage import ouvrir_fichier_local
from .text_extraction import extraire_texte

logger = logging.getLogger(__name__)
MAX_TEXTE_RESUME = 12_000
LONGUEUR_RESUME_MAX = 1_800

OUTIL_FICHE_PEDAGOGIQUE = {
    "type": "function",
    "function": {
        "name": "produire_fiche_pedagogique",
        "description": "Résume un document académique sans ajouter de faits absents du contenu.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "resume": {"type": "string"},
                "objectif_pedagogique": {"type": "string"},
                "type_cours": {"type": "string"},
                "niveau_cible": {"type": "string"},
                "notions_cles": {"type": "array", "items": {"type": "string"}},
                "competences_visees": {"type": "array", "items": {"type": "string"}},
                "prerequis": {"type": "array", "items": {"type": "string"}},
                "plan_cours": {"type": "array", "items": {"type": "string"}},
                "langue": {"type": "string"},
                "confiance": {"type": "number"},
            },
            "required": [
                "resume", "objectif_pedagogique", "type_cours", "niveau_cible",
                "notions_cles", "competences_visees", "prerequis", "plan_cours",
                "langue", "confiance",
            ],
        },
    },
}


def _normaliser(texte: str) -> str:
    valeur = unicodedata.normalize("NFKD", texte or "")
    valeur = "".join(c for c in valeur if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", valeur.lower()).strip()


def _client_ia() -> Optional[Groq]:
    if not parametres.groq_api_key:
        return None
    try:
        return Groq(api_key=parametres.groq_api_key)
    except Exception as erreur:
        logger.warning("Client IA fiche document indisponible (%s).", type(erreur).__name__)
        return None


def _nettoyer_liste(valeur: Any, limite: int = 8) -> list[str]:
    if not isinstance(valeur, list):
        return []
    resultat: list[str] = []
    vus: set[str] = set()
    for element in valeur:
        texte = re.sub(r"\s+", " ", str(element or "")).strip(" \t\r\n•-*")
        cle = _normaliser(texte)
        if not texte or not cle or cle in vus:
            continue
        vus.add(cle)
        resultat.append(texte[:180])
        if len(resultat) >= limite:
            break
    return resultat


def _type_cours_local(type_document: str, texte: str) -> str:
    contenu = _normaliser(texte)
    if re.search(r"\b(tp|travaux pratiques|laboratoire|manipulation)\b", contenu):
        return "Travaux pratiques (TP)"
    if re.search(r"\b(td|travaux diriges|exercices diriges)\b", contenu):
        return "Travaux dirigés (TD)"
    if "corrige" in contenu or "solution detaillee" in contenu:
        return "Corrigé ou solutions d'exercices"
    if "annale" in contenu or "sujet d examen" in contenu or "epreuve" in contenu:
        return "Sujet d'examen / annale"
    if "cours magistral" in contenu:
        return "Cours magistral"
    if type_document == "annale":
        return "Sujet d'examen / annale"
    if type_document == "corrige":
        return "Corrigé ou solutions d'exercices"
    if type_document == "fiche":
        return "Fiche de révision / synthèse"
    if type_document == "cours":
        return "Support de cours"
    return "Type détaillé à confirmer"


def _resume_local(titre: str, matiere: str, type_document: str, texte: str) -> dict[str, Any]:
    """Aperçu explicite et prudent lorsque la génération IA n'est pas possible."""
    compact = re.sub(r"[ \t]+", " ", (texte or "").replace("\x00", " "))
    lignes = [re.sub(r"\s+", " ", ligne).strip() for ligne in compact.splitlines()]
    candidates = [
        ligne for ligne in lignes
        if len(ligne) >= 28 and not re.fullmatch(r"[\d\s./-]{1,20}", ligne)
    ]
    if not candidates:
        brut = re.sub(r"\s+", " ", compact).strip()
        candidates = [brut] if len(brut) >= 28 else []

    if candidates:
        extraits: list[str] = []
        total = 0
        for ligne in candidates[:5]:
            ajout = ligne[:350]
            if total + len(ajout) > 950:
                ajout = ajout[: max(0, 950 - total)]
            if ajout:
                extraits.append(ajout)
                total += len(ajout)
            if total >= 950:
                break
        resume = ("Aperçu provisoire fondé sur le texte extrait : " + " ".join(extraits))[:LONGUEUR_RESUME_MAX]
        statut = "provisoire"
    else:
        resume = (
            "Le texte du fichier n'a pas pu être extrait de façon suffisante. "
            "La matière, le titre et le type indiquent le contexte général, "
            "mais le contenu exact doit être vérifié en ouvrant le document."
        )
        statut = "insuffisante"

    type_detail = _type_cours_local(type_document, texte)
    matiere_affichee = matiere.strip() if matiere and matiere.strip() else "matière non précisée"
    objectif = (
        f"Ce document concerne {matiere_affichee}. "
        "Les objectifs précis ne sont pas confirmés par une analyse IA du contenu ; "
        "consultez le document pour les valider."
    )
    if not candidates:
        objectif = (
            "Objectif pédagogique non déterminé : aucun texte exploitable n'a pu être "
            "extrait. Ouvrez le fichier pour confirmer ce qu'il vise."
        )

    return {
        "resume": resume,
        "objectif_pedagogique": objectif,
        "type_cours": type_detail,
        "niveau_cible": "Niveau non déterminé à partir du contenu disponible",
        "notions_cles": [],
        "competences_visees": [],
        "prerequis": [],
        "plan_cours": [],
        "langue": "Langue à confirmer",
        "confiance": 0.25 if candidates else 0.0,
        "source": "local",
        "statut": statut,
        "limites": (
            "Aperçu provisoire : certaines informations pédagogiques restent à confirmer."
            if candidates else
            "Le fichier n'a pas fourni de texte suffisamment exploitable ; aucune notion ou aucun niveau n'a été inventé."
        ),
    }


def _normaliser_reponse_ia(
    donnees: dict[str, Any],
    *,
    titre: str,
    matiere: str,
    type_document: str,
    texte: str,
) -> dict[str, Any]:
    fallback = _resume_local(titre, matiere, type_document, texte)
    resume = re.sub(r"\s+", " ", str(donnees.get("resume") or "")).strip()
    objectif = re.sub(r"\s+", " ", str(donnees.get("objectif_pedagogique") or "")).strip()
    type_cours = re.sub(r"\s+", " ", str(donnees.get("type_cours") or "")).strip()
    niveau = re.sub(r"\s+", " ", str(donnees.get("niveau_cible") or "")).strip()
    langue = re.sub(r"\s+", " ", str(donnees.get("langue") or "")).strip()
    try:
        confiance = max(0.0, min(1.0, float(donnees.get("confiance") or 0)))
    except (TypeError, ValueError):
        confiance = 0.0

    if not resume:
        return fallback
    return {
        "resume": resume[:LONGUEUR_RESUME_MAX],
        "objectif_pedagogique": (objectif or "Objectifs non précisés explicitement dans le texte disponible.")[:900],
        "type_cours": (type_cours or fallback["type_cours"])[:140],
        "niveau_cible": (niveau or "Niveau non déterminé à partir du contenu disponible")[:140],
        "notions_cles": _nettoyer_liste(donnees.get("notions_cles")),
        "competences_visees": _nettoyer_liste(donnees.get("competences_visees")),
        "prerequis": _nettoyer_liste(donnees.get("prerequis")),
        "plan_cours": _nettoyer_liste(donnees.get("plan_cours"), limite=10),
        "langue": (langue or "Langue à confirmer")[:80],
        "confiance": confiance,
        "source": "ia",
        "statut": "generee",
        "limites": "",
    }


def generer_fiche_pedagogique(
    *,
    nom_fichier: str,
    titre: str,
    matiere: str,
    type_document: str,
    annee: int,
    filiere: str,
    texte: str,
) -> dict[str, Any]:
    """Crée une fiche exploitable et signale clairement tout mode dégradé."""
    contenu = (texte or "").strip()[:MAX_TEXTE_RESUME]
    client = _client_ia() if len(contenu) >= 100 else None
    if client is None:
        return _resume_local(titre, matiere, type_document, contenu)

    contexte = (
        f"Titre : {titre}\nMatière déclarée : {matiere}\nType de document : {type_document}\n"
        f"Année : {annee}\nFilière : {filiere or 'non précisée'}\n"
        f"Nom de fichier : {Path(nom_fichier or 'document').name}\n\n"
        f"Texte extrait (extrait limité, pas nécessairement le document entier) :\n{contenu}"
    )
    prompt = (
        "Tu es un assistant pédagogique pour la bibliothèque universitaire MITARIDALA. "
        "Produis une fiche de lecture destinée à un étudiant qui veut décider si cette ressource "
        "correspond à son cours. Écris en français clair. Résume le contenu, indique l'objectif "
        "pédagogique, le type détaillé (cours théorique, TD, TP, fiche, annale, correction, etc.), "
        "les notions clés, compétences, prérequis, plan et langue seulement quand le contenu permet "
        "de les identifier. N'invente jamais le niveau d'étude, un chapitre, des exercices, des "
        "références, un programme officiel ou des objectifs absents. Si le niveau n'est pas explicite, "
        "réponds « Niveau non déterminé à partir du contenu disponible ». Si une information manque, "
        "signale-le clairement et laisse ses listes vides. Le résumé doit paraphraser, éviter de "
        "recopier de longs passages, et rester entre 70 et 140 mots quand le texte le permet.\n\n"
        + contexte
    )
    try:
        completion = client.chat.completions.create(
            model=parametres.groq_model,
            max_completion_tokens=1300,
            reasoning_effort="low",
            include_reasoning=False,
            tools=[OUTIL_FICHE_PEDAGOGIQUE],
            tool_choice={"type": "function", "function": {"name": "produire_fiche_pedagogique"}},
            messages=[{"role": "user", "content": prompt}],
        )
        message = completion.choices[0].message
        if not message.tool_calls:
            return _resume_local(titre, matiere, type_document, contenu)
        donnees = json.loads(message.tool_calls[0].function.arguments)
        if not isinstance(donnees, dict):
            return _resume_local(titre, matiere, type_document, contenu)
        return _normaliser_reponse_ia(
            donnees, titre=titre, matiere=matiere, type_document=type_document, texte=contenu
        )
    except Exception as erreur:
        logger.warning("Génération de fiche documentaire en mode provisoire (%s).", type(erreur).__name__)
        return _resume_local(titre, matiere, type_document, contenu)


def generer_et_sauvegarder_fiche_document(document_id: int) -> None:
    """Worker durable : extrait le document, puis persiste sa fiche pédagogique."""
    with Session(engine) as session:
        document = session.get(Document, document_id)
        if not document:
            raise RuntimeError(f"Document #{document_id} introuvable.")
        if document.resume_ia and document.resume_statut_ia in {
            "generee", "provisoire", "insuffisante"
        }:
            return
        document.resume_statut_ia = "en_cours"
        session.add(document)
        session.commit()
        donnees_document = {
            "chemin_fichier": document.chemin_fichier,
            "nom_fichier": Path(document.chemin_fichier).name,
            "titre": document.titre,
            "matiere": document.matiere,
            "type_document": document.type_document.value,
            "annee": document.annee,
            "filiere_id": document.filiere_id,
        }

    texte = ""
    try:
        with ouvrir_fichier_local(donnees_document["chemin_fichier"]) as chemin_local:
            texte = extraire_texte(str(chemin_local)) or ""
    except Exception as erreur:
        logger.warning(
            "Extraction du texte du document #%s impossible (%s).",
            document_id,
            type(erreur).__name__,
        )

    with Session(engine) as session:
        filiere = session.get(Filiere, donnees_document["filiere_id"])
        nom_filiere = filiere.nom if filiere else ""

    fiche = generer_fiche_pedagogique(
        nom_fichier=donnees_document["nom_fichier"],
        titre=donnees_document["titre"],
        matiere=donnees_document["matiere"],
        type_document=donnees_document["type_document"],
        annee=donnees_document["annee"],
        filiere=nom_filiere,
        texte=texte,
    )
    with Session(engine) as session:
        document = session.get(Document, document_id)
        if not document:
            raise RuntimeError(f"Document #{document_id} supprimé pendant le traitement.")
        document.resume_ia = fiche["resume"]
        document.fiche_pedagogique_json = json.dumps(fiche, ensure_ascii=False)
        document.resume_statut_ia = fiche["statut"]
        document.resume_genere_le = datetime.utcnow()
        session.add(document)
        session.commit()
    logger.info(
        "Fiche pédagogique enregistrée pour document #%s (mode=%s, statut=%s).",
        document_id, fiche.get("source", "inconnu"), fiche.get("statut", "inconnu")
    )
