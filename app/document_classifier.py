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
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, Sequence

from groq import Groq

from .config import parametres
from .models import Filiere, TypeDocument

logger = logging.getLogger(__name__)

MAX_TEXTE_IA = 16_000
MAX_TITRE = 180

ALIASES_MATIERES = {
    "Mathématiques": ("mathematiques", "mathematique", "maths", "algebre", "geometrie", "equations differentielles", "calcul integral"),
    "Physique": ("physique", "mecanique", "electricite", "optique", "thermodynamique"),
    "Chimie": ("chimie", "chimique", "chimie organique", "chimie minerale"),
    "Biologie": ("biologie", "svt", "anatomie", "physiologie", "botanique", "zoologie"),
    "Français": ("francais", "grammaire", "conjugaison", "litterature francaise", "redaction"),
    "Malagasy": ("malagasy", "malgache", "teny malagasy"),
    "Anglais": ("anglais", "english"),
    "Histoire": ("histoire", "histoire contemporaine", "histoire ancienne"),
    "Géographie": ("geographie", "cartographie", "geographie humaine"),
    "Philosophie": ("philosophie", "philosophique"),
    "Droit": ("droit civil", "droit penal", "droit public", "droit prive", "juridique", "jurisprudence"),
    "Économie": ("economie", "economique", "microeconomie", "macroeconomie"),
    "Comptabilité": ("comptabilite", "comptable", "comptes annuels"),
    "Informatique": ("informatique", "programmation", "algorithmique", "developpement logiciel", "bases de donnees"),
    "Gestion": ("gestion", "management", "administration des entreprises"),
    "Marketing": ("marketing", "communication commerciale"),
    "Psychologie": ("psychologie", "psychologique"),
    "Éducation civique": ("education civique", "instruction civique", "education a la citoyennete"),
}


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
    stem = Path(nom_fichier or "").stem.replace("_", " ").replace("-", " ")
    stem = re.sub(r"(?<!\d)(?:20\d{2}|19\d{2})(?!\d)", " ", stem)
    valeur = _nettoyer_titre(stem)
    if not valeur or not any(char.isalpha() for char in valeur):
        return None
    if _normaliser(valeur) in {"document", "fichier", "scan", "scanne", "cours", "annale"}:
        return None
    return valeur


def _titre_depuis_texte(texte: str) -> Optional[str]:
    """Retient un en-tête plausible quand le nom de fichier est générique."""
    exclusions = (
        "universite ", "republique ", "ministere ", "faculte ",
        "annee ", "session ", "matiere ", "discipline ", "module ",
        "document de travail", "table des matieres", "type de document",
        "epreuve ", "examen ", "annale ", "annales ", "corrige ", "corriges ",
        "sujet ", "nom et prenom", "nom :", "prenom :", "duree ", "coefficient ",
        "ufr ", "departement ", "etablissement ", "ecole ",
    )
    for ligne in (texte or "").splitlines()[:35]:
        ligne_brute = " ".join(str(ligne or "").split())
        # Une phrase explicative terminée par une ponctuation n'est pas un titre.
        if re.search(r"[.!?;:]\\s*$", ligne_brute):
            continue
        valeur = _nettoyer_titre(ligne_brute)
        if not valeur or len(valeur) < 8 or len(valeur) > 120:
            continue
        normalise = _normaliser(valeur)
        if any(normalise.startswith(item) for item in exclusions):
            continue
        if len(normalise.split()) > 14 or re.fullmatch(r"[\d\s./-]+", valeur):
            continue
        if sum(char.isalpha() for char in valeur) < 6:
            continue
        return valeur
    return None


def _matiere_depuis_nom_fichier(nom_fichier: str) -> Optional[str]:
    """Extrait une matière courte et plausible depuis le nom du fichier."""
    stem = Path(nom_fichier or "").stem.replace("_", " ").replace("-", " ")
    if not stem:
        return None

    # Les marqueurs de type ne font pas partie de la matière.
    stem = re.sub(
        r"^(?:cours|support|annale|corrig[ée]|corrige|fiche|td|tp|examen|épreuve|epreuve|partiel|devoir|scan|scanne|scanned)\s*[-_: ]*",
        "",
        stem,
        flags=re.I,
    )
    stem = re.sub(r"(?<!\d)(?:19|20)\d{2}(?!\d)", " ", stem)
    stem = re.sub(r"(?<![a-z0-9])(?:s[1-9]|l[1-3]|m[1-2])(?![a-z0-9])", " ", stem, flags=re.I)
    stem = re.sub(
        r"(?:annale|corrige|corrigé|fiche|cours|support|examen|epreuve|épreuve|scan|scanne)$",
        " ",
        stem,
        flags=re.I,
    )
    stem = stem.replace("_", " ").replace("-", " ")
    stem = re.sub(r"\s+", " ", stem).strip(" .:-_")

    if not stem:
        return None
    stem_normalise = _normaliser(stem)
    alias_generiques = {
        _normaliser(alias)
        for alias in (
            "mathématiques", "mathématique", "maths", "physique", "chimie",
            "biologie", "svt", "français", "malagasy", "malgache", "anglais",
            "histoire", "géographie", "philosophie", "droit", "économie",
            "comptabilité", "informatique", "gestion", "marketing",
            "psychologie", "éducation civique",
        )
    }
    if stem_normalise in alias_generiques:
        # "scan_maths.pdf" doit devenir la matière canonique, pas "maths"
        # ou "scan maths" déduit mécaniquement du nom du fichier.
        return None
    return _matiere_auto_valide(stem)


def _annee_depuis_texte(*sources: str) -> Optional[int]:
    """Privilégie la session, puis l'année scolaire, au nom du fichier."""
    textes = [_normaliser(source or "") for source in sources]

    # La session est plus précise qu'une année dans le nom ou un copyright.
    for texte in textes:
        correspondance = re.search(
            r"\bsession\s*(?:normale|rattrapage|extraordinaire)?\s*(?:de\s*)?((?:19|20)\d{2})\b",
            texte,
        )
        if correspondance:
            annee = int(correspondance.group(1))
            if 2000 <= annee <= 2100:
                return annee

    # Pour 2025-2026, on retient l'année de fin : 2026.
    for texte in textes:
        correspondance = re.search(
            r"\bannee(?: scolaire| academique| universitaire)?\s*"
            r"((?:19|20)\d{2})(?:\s+((?:19|20)\d{2}))?\b",
            texte,
        )
        if correspondance:
            annee = int(correspondance.group(2) or correspondance.group(1))
            if 2000 <= annee <= 2100:
                return annee

    for texte in textes:
        for valeur in re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", texte):
            annee = int(valeur)
            if 2000 <= annee <= 2100:
                return annee
    return None


def _type_local(texte: str) -> Optional[TypeDocument]:
    """Détecte des expressions complètes pour réduire les faux positifs."""
    normalise = f" {_normaliser(texte)} "

    def contient(*expressions: str) -> bool:
        return any(f" {expression} " in normalise for expression in expressions)

    if contient(
        "corrige", "corriges", "correction", "corrections", "solution", "solutions",
        "corrige type", "reponse type", "reponses types",
    ):
        return TypeDocument.CORRIGE
    if contient(
        "annale", "annales", "examen", "examens", "ancien examen", "sujet examen",
        "epreuve", "epreuves", "epreuve finale", "partiel", "partiels",
        "examen session", "session normale", "session rattrapage",
        "devoir surveille", "devoirs surveilles", "composition", "compositions",
        "controle continu",
    ):
        return TypeDocument.ANNALE
    if contient(
        "fiche de revision", "fiches de revision", "fiche revision",
        "resume", "resumes", "synthese", "syntheses", "memo revision",
        "cheat sheet",
    ):
        return TypeDocument.FICHE
    if contient(
        "cours", "chapitre", "chapitres", "support de cours", "supports de cours",
        "polycopie", "polycopies", "notes de cours", "travaux diriges",
        "travaux pratiques",
    ):
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


def _score_filiere(nom_filiere: str, texte_normalise: str) -> int:
    nom = _normaliser(nom_filiere)
    if not nom or not texte_normalise:
        return 0
    contenu = f" {texte_normalise} "
    if len(nom) >= 5 and f" {nom} " in contenu:
        return 120 + len(nom)

    stopwords = {
        "de", "du", "des", "et", "la", "le", "les", "en", "a", "au", "aux",
        "faculte", "universite", "universitaire", "departement", "formation",
        "sciences", "etudes", "licence", "master",
    }
    tokens = {mot for mot in nom.split() if len(mot) >= 3 and mot not in stopwords}
    if not tokens:
        tokens = {mot for mot in nom.split() if len(mot) >= 5}
    if not tokens:
        return 0

    mots_contenu = set(texte_normalise.split())
    correspondants = set()
    for token in tokens:
        if token in mots_contenu:
            correspondants.add(token)
            continue
        if len(token) >= 6 and any(
            len(mot) >= 6 and SequenceMatcher(None, token, mot).ratio() >= 0.90
            for mot in mots_contenu
        ):
            correspondants.add(token)

    ratio = len(correspondants) / len(tokens)
    if ratio == 1:
        return 88 + 3 * len(tokens)
    if ratio >= 0.67 and len(tokens) >= 2:
        return 45 + int(20 * ratio) + len(correspondants)
    return 0


def _candidats_filieres(texte: str, filieres: Sequence[Filiere], limite: int = 12) -> list[Filiere]:
    contenu = _normaliser(texte)
    if not contenu:
        return []
    scores = [
        (_score_filiere(filiere.nom, contenu), len(_normaliser(filiere.nom)), filiere)
        for filiere in filieres
    ]
    scores = [item for item in scores if item[0] > 0]
    scores.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in scores[:limite]]


def _matiere_depuis_signaux(nom_fichier: str, texte: str) -> Optional[str]:
    """Repère les matières connues sans transformer une phrase en matière."""
    nom = _normaliser(Path(nom_fichier or "").stem)
    lignes_hautes = _normaliser("\n".join((texte or "").splitlines()[:35]))
    contenu = _normaliser(texte or "")
    scores: list[tuple[int, str]] = []
    for matiere, alias in ALIASES_MATIERES.items():
        score = 0
        for valeur in alias:
            cle = _normaliser(valeur)
            if not cle:
                continue
            if f" {cle} " in f" {nom} ":
                score += 10
            if f" {cle} " in f" {lignes_hautes} ":
                score += 6
            elif f" {cle} " in f" {contenu} ":
                score += 2
        if score:
            scores.append((score, matiere))
    scores.sort(reverse=True)
    if not scores or scores[0][0] < 5:
        return None
    if len(scores) > 1 and scores[0][0] - scores[1][0] < 3:
        return None
    return scores[0][1]


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
        "Tu es le classificateur de documents de MITARIDALA. "
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
    type_local = type_local_texte or type_local_nom
    annee_local = _annee_depuis_texte(texte, nom_fichier)

    candidats = _candidats_filieres(texte_reference, filieres)
    meilleur_filiere = candidats[0] if candidats else None
    texte_normalise = _normaliser(texte_reference)
    if meilleur_filiere and _score_filiere(meilleur_filiere.nom, texte_normalise) < 80:
        meilleur_filiere = None
    if len(candidats) > 1 and meilleur_filiere:
        score_1 = _score_filiere(candidats[0].nom, texte_normalise)
        score_2 = _score_filiere(candidats[1].nom, texte_normalise)
        if score_1 - score_2 < 12:
            meilleur_filiere = None

    resultat_ia = _classification_ia(nom_fichier, texte, candidats)
    confiance_ia = float(resultat_ia.get("confiance") or 0.0)
    confiance_ia = max(0.0, min(1.0, confiance_ia))

    titre = (
        _nettoyer_titre(resultat_ia.get("titre") or "")
        or titre_local
        or _nettoyer_titre(titre_fourni)
        or _titre_depuis_texte(texte)
    )

    # L'IA peut parfois recopier une phrase du cours comme "matière".
    # On refuse ces sorties trop longues/phrastiques et on utilise le nom
    # du fichier comme signal de secours (ex. "Cours-algèbre.pdf" -> "algèbre").
    matiere_ia = _matiere_auto_valide(resultat_ia.get("matiere") or "")
    matiere = (
        matiere_local
        or matiere_local_nom
        or _matiere_depuis_signaux(nom_fichier, texte)
        or matiere_ia
        or _matiere_auto_valide(titre_local or "")
        or _nettoyer_titre(matiere_fourni)
    )

    # Une matière canonique reconnue par alias (par ex. "maths" ->
    # "Mathématiques") doit aussi retrouver son entrée exacte dans le
    # référentiel. C'est essentiel pour ne pas rejeter un lot scolaire valide
    # lorsque le nom du fichier emploie une abréviation.
    if matiere:
        correspondances_matiere = [
            filiere for filiere in filieres
            if _normaliser(filiere.nom) == _normaliser(matiere)
        ]
        if len(correspondances_matiere) == 1:
            meilleur_filiere = correspondances_matiere[0]

    type_auto = None
    try:
        if resultat_ia.get("type_document"):
            type_auto = TypeDocument(resultat_ia["type_document"])
    except (ValueError, TypeError):
        type_auto = None

    type_document = type_local_texte or type_local_nom or type_auto or type_fourni

    annee_ia = None
    try:
        valeur_annee = int(resultat_ia.get("annee") or 0)
        if 2000 <= valeur_annee <= 2100:
            annee_ia = valeur_annee
    except (ValueError, TypeError):
        annee_ia = None
    annee = annee_local or annee_ia or annee_fournie

    nom_ia = _normaliser(str(resultat_ia.get("filiere_nom") or ""))
    filiere_ia_id = None
    if nom_ia:
        for filiere in candidats:
            if _normaliser(filiere.nom) == nom_ia:
                filiere_ia_id = filiere.id
                break
    filiere_id_auto = (
        filiere_ia_id
        or (meilleur_filiere.id if meilleur_filiere is not None else None)
    )
    # Une valeur manuelle reste prioritaire sur une proposition automatique.
    filiere_id = (
        filiere_id_fournie
        if filiere_id_fournie is not None else filiere_id_auto
    )

    # Le score représente les éléments trouvés dans le fichier, pas les
    # champs manuels utilisés comme valeurs de secours.
    titre_auto_detecte = bool(
        resultat_ia.get("titre") or titre_local or _titre_depuis_texte(texte)
    )
    matiere_auto_detectee = bool(
        matiere_local
        or matiere_local_nom
        or _matiere_depuis_signaux(nom_fichier, texte)
        or matiere_ia
        or _matiere_auto_valide(titre_local or "")
    )
    type_auto_detecte = bool(type_local_nom or type_local_texte or type_auto)
    annee_auto_detectee = bool(annee_local or annee_ia)
    filiere_auto_detectee = filiere_id_auto is not None
    ia_a_fourni_un_indice = any((
        resultat_ia.get("titre"),
        resultat_ia.get("matiere"),
        type_auto,
        annee_ia,
        filiere_ia_id,
    ))

    # Une confiance IA explicitement basse n'autorise pas une réécriture
    # agressive du choix utilisateur pour les champs ambigus.
    if resultat_ia and confiance_ia < 0.55:
        titre = (
            _nettoyer_titre(titre_fourni)
            or titre_local
            or _titre_depuis_texte(texte)
        )
        matiere = (
            _nettoyer_titre(matiere_fourni)
            or matiere_local
            or matiere_local_nom
            or _matiere_depuis_signaux(nom_fichier, texte)
            or _matiere_auto_valide(titre_local or "")
        )
        type_document = type_local_nom or type_local_texte or type_fourni
        annee = annee_local or annee_fournie
        # Un score IA faible ne doit pas annuler un rapprochement local fort
        # entre le contenu et un élément du référentiel (filière ou matière).
        filiere_id = (
            filiere_id_fournie
            or (meilleur_filiere.id if meilleur_filiere is not None else None)
        )

    return ClassificationDocument(
        titre=titre,
        matiere=matiere,
        type_document=type_document,
        annee=annee,
        filiere_id=filiere_id,
        confiance=round(max(
            confiance_ia if ia_a_fourni_un_indice else 0.0,
            sum((
                0.18 if titre_auto_detecte else 0.0,
                0.25 if matiere_auto_detectee else 0.0,
                0.18 if type_auto_detecte else 0.0,
                0.15 if annee_auto_detectee else 0.0,
                0.16 if filiere_auto_detectee else 0.0,
                0.08 if len((texte or "").strip()) >= 120 else 0.0,
            )),
        ), 3),
        source="groq+locale" if resultat_ia else "locale",
    )
