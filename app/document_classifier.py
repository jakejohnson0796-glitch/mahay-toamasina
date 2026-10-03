"""Détection et classification assistées des documents déposés.

Le module reste prudent : il privilégie les indices déterministes locaux,
puis utilise Groq uniquement quand la détection automatique est demandée et
qu'une clé IA est configurée. L'IA reçoit seulement un extrait borné du
document et les filières candidates déjà trouvées localement.

Aucune décision de modération n'est prise ici : la sortie sert uniquement
à renseigner les métadonnées existantes du modèle Document.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Optional, Sequence

from groq import Groq

from .config import parametres
from .models import Filiere, TypeDocument

logger = logging.getLogger(__name__)

MAX_TEXTE_IA = 12_000
MAX_TITRE = 180


@dataclass(frozen=True)
class ClassificationDocument:
    titre: Optional[str] = None
    matiere: Optional[str] = None
    type_document: Optional[TypeDocument] = None
    annee: Optional[int] = None
    filiere_id: Optional[int] = None
    confiance: float = 0.0
    source: str = "locale"


def _normaliser(texte: str) -> str:
    valeur = unicodedata.normalize("NFKD", texte or "")
    valeur = "".join(c for c in valeur if not unicodedata.combining(c))
    valeur = valeur.lower()
    valeur = re.sub(r"[^a-z0-9]+", " ", valeur)
    return re.sub(r"\s+", " ", valeur).strip()


def _nettoyer_titre(texte: str) -> Optional[str]:
    if not texte:
        return None
    valeur = " ".join(str(texte).replace("_", " ").replace("-", " ").split())
    valeur = re.sub(r"^(document|cours|support|scan|scanne)\s*[:_-]?\s*", "", valeur, flags=re.I)
    if not valeur:
        return None
    if _normaliser(valeur) in {"document", "fichier", "scan", "scanne", "cours"}:
        return None
    if len(valeur) > MAX_TITRE:
        valeur = valeur[: MAX_TITRE - 1].rsplit(" ", 1)[0] + "…"
    return valeur.strip(" .:-") or None


def _titre_depuis_nom(nom_fichier: str) -> Optional[str]:
    stem = Path(nom_fichier or "").stem
    stem = re.sub(r"\b(20\d{2}|19\d{2})\b", " ", stem)
    return _nettoyer_titre(stem)


def _matiere_depuis_nom_fichier(nom_fichier: str) -> Optional[str]:
    """Extrait une matière courte et plausible depuis le nom du fichier."""
    stem = Path(nom_fichier or "").stem
    if not stem:
        return None

    # Les marqueurs de type ne font pas partie de la matière.
    stem = re.sub(
        r"^(?:cours|support|annale|corrig[ée]|corrige|fiche|td|tp)\s*[-_: ]\s*",
        "",
        stem,
        flags=re.I,
    )
    stem = re.sub(r"\b(?:19|20)\d{2}\b", " ", stem)
    stem = re.sub(r"\b(?:s[1-9]|l[1-3]|m[1-2])\b", " ", stem, flags=re.I)
    stem = stem.replace("_", " ").replace("-", " ")
    stem = re.sub(r"\s+", " ", stem).strip(" .:-_")

    if not stem:
        return None
    return _matiere_auto_valide(stem)


def _annee_depuis_texte(*sources: str) -> Optional[int]:
    for source in sources:
        for valeur in re.findall(r"\b(?:19|20)\d{2}\b", source or ""):
            annee = int(valeur)
            if 2000 <= annee <= 2100:
                return annee
    return None


def _type_local(texte: str) -> Optional[TypeDocument]:
    normalise = _normaliser(texte)
    if any(x in normalise for x in (
        "corrige", "correction", "solution", "corrigé", "solutions"
    )):
        return TypeDocument.CORRIGE
    if any(x in normalise for x in (
        "annale", "ancien examen", "sujet examen", "epreuve", "partiel",
        "examen session", "session normale", "session rattrapage",
    )):
        return TypeDocument.ANNALE
    if any(x in normalise for x in (
        "fiche de revision", "fiche revision", "resume", "synthese",
        "memo revision", "cheat sheet",
    )):
        return TypeDocument.FICHE
    if any(x in normalise for x in (
        "cours", "chapitre", "support de cours", "polycopie", "notes de cours",
    )):
        return TypeDocument.COURS
    return None


def _matiere_auto_valide(texte: str) -> Optional[str]:
    """Accepte seulement une matière courte et plausible, pas une phrase de cours."""
    valeur = _nettoyer_titre(texte)
    if not valeur:
        return None

    normalise = _normaliser(valeur)
    mots = normalise.split()
    if len(mots) < 2 and len(normalise) < 4:
        return None
    if len(mots) > 8 or len(valeur) > 80:
        return None
    if re.match(r"^(?:[•\-*]\s+|\d{1,3}[.)]\s+|[a-z][.)]\s+|\([a-z0-9]+[.)]?\)\s+)", valeur, flags=re.I):
        return None
    if re.search(r"[.!?;:][\s$]", valeur):
        return None
    if re.search(r"\b(?:si|alors|donc|est|sont|vaut|soit|pour|lorsque|ainsi)\b", normalise) and len(mots) >= 5:
        return None
    return valeur


def _matiere_locale(texte: str) -> Optional[str]:
    motifs = (
        r"(?:mati[eè]re|module|unit[eé] d['’]enseignement|ue)\s*[:=-]\s*([^\n|]{3,100})",
        r"(?:discipline|th[eè]me)\s*[:=-]\s*([^\n|]{3,100})",
    )
    for motif in motifs:
        match = re.search(motif, texte or "", re.I)
        if match:
            valeur = _nettoyer_titre(match.group(1))
            if valeur and len(_normaliser(valeur)) > 2:
                return valeur
    return None


def _candidats_filieres(texte: str, filieres: Sequence[Filiere], limite: int = 12) -> list[Filiere]:
    contenu = _normaliser(texte)
    if not contenu:
        return []

    mots = set(contenu.split())
    scores: list[tuple[int, int, Filiere]] = []
    for filiere in filieres:
        nom = _normaliser(filiere.nom)
        if not nom:
            continue
        nom_mots = set(nom.split())
        score = 0
        if len(nom) >= 5 and nom in contenu:
            score += 100 + len(nom)
        score += sum(2 for mot in nom_mots if len(mot) >= 4 and mot in mots)
        if score > 0:
            scores.append((score, len(nom), filiere))
    scores.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in scores[:limite]]


def _client_ia() -> Optional[Groq]:
    if not parametres.groq_api_key:
        return None
    try:
        return Groq(api_key=parametres.groq_api_key)
    except Exception as erreur:
        logger.warning("Classification document: client Groq indisponible (%s)", type(erreur).__name__)
        return None


OUTIL_CLASSIFICATION = {
    "type": "function",
    "function": {
        "name": "classifier_document",
        "description": "Retourne uniquement les métadonnées détectées d'un document académique.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "titre": {"type": "string"},
                "matiere": {"type": "string"},
                "type_document": {
                    "type": "string",
                    "enum": [item.value for item in TypeDocument],
                },
                "annee": {"type": "integer"},
                "filiere_nom": {"type": "string"},
                "confiance": {"type": "number"},
            },
            "required": ["titre", "matiere", "type_document", "annee", "filiere_nom", "confiance"],
        },
    },
}


def _classification_ia(
    nom_fichier: str,
    texte: str,
    candidats: Sequence[Filiere],
) -> dict:
    client = _client_ia()
    if client is None:
        return {}

    catalogue = "\n".join(
        f"- {filiere.nom}" for filiere in candidats
    ) or "- Aucune filière candidate trouvée"

    prompt = (
        "Tu es le classificateur de documents de Gasy Mahay. "
        "Tu dois renseigner des métadonnées sans rien inventer. "
        "Si une information est absente ou ambiguë, laisse-la vide et mets une confiance basse.\n\n"
        f"Nom du fichier : {nom_fichier}\n\n"
        "Filières candidates trouvées localement :\n"
        f"{catalogue}\n\n"
        "Extrait du document (tronqué) :\n"
        f"{(texte or '')[:MAX_TEXTE_IA]}"
    )
    try:
        completion = client.chat.completions.create(
            model=parametres.groq_model,
            max_completion_tokens=700,
            reasoning_effort="low",
            include_reasoning=False,
            tools=[OUTIL_CLASSIFICATION],
            tool_choice={"type": "function", "function": {"name": "classifier_document"}},
            messages=[{"role": "user", "content": prompt}],
        )
        message = completion.choices[0].message
        if not message.tool_calls:
            return {}
        return json.loads(message.tool_calls[0].function.arguments)
    except Exception as erreur:
        logger.warning(
            "Classification document: appel IA échoué type=%s",
            type(erreur).__name__,
        )
        return {}


def classifier_document(
    *,
    nom_fichier: str,
    texte: str,
    filieres: Sequence[Filiere],
    titre_fourni: str = "",
    matiere_fourni: str = "",
    type_fourni: Optional[TypeDocument] = None,
    annee_fournie: Optional[int] = None,
    filiere_id_fournie: Optional[int] = None,
) -> ClassificationDocument:
    """Produit les métadonnées finales à enregistrer.

    La valeur fournie par l'utilisateur reste le fallback. Les déductions
    automatiques ne remplacent une valeur que lorsqu'elles sont exploitables.
    """
    texte_reference = f"{nom_fichier}\n{texte or ''}"
    titre_local = _titre_depuis_nom(nom_fichier)
    matiere_local = _matiere_locale(texte_reference)
    matiere_local_nom = _matiere_depuis_nom_fichier(nom_fichier)
    type_local_nom = _type_local(nom_fichier)
    type_local_texte = _type_local(texte)
    type_local = type_local_nom or type_local_texte
    annee_local = _annee_depuis_texte(nom_fichier, texte)

    candidats = _candidats_filieres(texte_reference, filieres)
    meilleur_filiere = candidats[0] if candidats else None
    if meilleur_filiere and _normaliser(meilleur_filiere.nom) not in _normaliser(texte_reference):
        meilleur_filiere = None

    resultat_ia = _classification_ia(nom_fichier, texte, candidats)
    confiance_ia = float(resultat_ia.get("confiance") or 0.0)
    confiance_ia = max(0.0, min(1.0, confiance_ia))

    titre = _nettoyer_titre(resultat_ia.get("titre") or "") or titre_local or _nettoyer_titre(titre_fourni)

    # L'IA peut parfois recopier une phrase du cours comme "matière".
    # On refuse ces sorties trop longues/phrastiques et on utilise le nom
    # du fichier comme signal de secours (ex. "Cours-algèbre.pdf" -> "algèbre").
    matiere_ia = _matiere_auto_valide(resultat_ia.get("matiere") or "")
    matiere = (
        matiere_local_nom
        or matiere_ia
        or matiere_local
        or _matiere_auto_valide(titre_local or "")
        or _nettoyer_titre(matiere_fourni)
    )

    type_auto = None
    try:
        if resultat_ia.get("type_document"):
            type_auto = TypeDocument(resultat_ia["type_document"])
    except (ValueError, TypeError):
        type_auto = None

    type_document = type_local_nom or type_local_texte or type_auto or type_fourni

    annee = None
    try:
        valeur_annee = int(resultat_ia.get("annee") or 0)
        if 2000 <= valeur_annee <= 2100:
            annee = valeur_annee
    except (ValueError, TypeError):
        annee = None
    annee = annee_local or annee or annee_fournie

    filiere_id = filiere_id_fournie
    nom_ia = _normaliser(str(resultat_ia.get("filiere_nom") or ""))
    if nom_ia:
        for filiere in candidats:
            if _normaliser(filiere.nom) == nom_ia:
                filiere_id = filiere.id
                break
    if filiere_id is None and meilleur_filiere is not None:
        filiere_id = meilleur_filiere.id

    auto_utilisee = any(
        valeur is not None
        for valeur in (
            resultat_ia.get("titre"),
            resultat_ia.get("matiere"),
            type_auto,
            annee,
            nom_ia,
        )
    )

    # Une confiance IA explicitement basse n'autorise pas une réécriture
    # agressive du choix utilisateur pour les champs ambigus.
    if resultat_ia and confiance_ia < 0.55:
        titre = _nettoyer_titre(titre_fourni) or titre_local
        matiere = (
            _nettoyer_titre(matiere_fourni)
            or matiere_local_nom
            or matiere_local
            or _matiere_auto_valide(titre_local or "")
        )
        type_document = type_local_nom or type_local_texte or type_fourni
        annee = annee_local or annee_fournie
        filiere_id = filiere_id_fournie

    return ClassificationDocument(
        titre=titre,
        matiere=matiere,
        type_document=type_document,
        annee=annee,
        filiere_id=filiere_id,
        confiance=confiance_ia if auto_utilisee and resultat_ia else (
            0.75 if meilleur_filiere or type_local or annee_local or titre_local else 0.0
        ),
        source="groq+locale" if resultat_ia else "locale",
    )
