"""Extraction structurée et contrôles de provenance des programmes EP/FRP."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit

MAX_ELEMENTS_PROPOSES = 250
MAX_TEXTE_ELEMENT = 100_000
MIN_TEXTE_VALIDABLE = 80


def extraction_validable_apres_controle_manuel(nombre_caracteres: int, original_verifie: bool) -> bool:
    """Autorise une extraction insuffisante seulement après lecture explicite de l’original."""
    return nombre_caracteres >= MIN_TEXTE_VALIDABLE or bool(original_verifie)
DOMAINES_OFFICIELS = (
    "education.gov.mg",
    "plateforme.education.gov.mg",
    "plateforme.education.mg",
    "metfp.gov.mg",
)


def est_source_officielle(url: str | None) -> bool:
    """N'accepte que les domaines ministériels reconnus, en HTTPS strict."""
    if not url:
        return False
    try:
        parsed = urlsplit(url.strip())
        hostname = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
        return (
            parsed.scheme == "https"
            and bool(hostname)
            and parsed.username is None
            and parsed.password is None
            and port in (None, 443)
            and any(
                hostname == domaine or hostname.endswith("." + domaine)
                for domaine in DOMAINES_OFFICIELS
            )
        )
    except ValueError:
        return False


def _nettoyer_ligne(ligne: str) -> str:
    return " ".join((ligne or "").replace("\x00", "").split()).strip()


def _identifier_titre(ligne: str) -> tuple[str, str, str] | None:
    """Retourne (type, code source, titre) uniquement pour un titre explicite."""
    motifs = (
        (
            "chapitre",
            re.compile(
                r"^(?:CHAPITRE|CHAP\.?|PARTIE|UNIT[ÉE])\s+"
                r"([0-9IVXLCDM]+)\s*[:.\-–—)]*\s*(.*)$",
                re.IGNORECASE,
            ),
        ),
        (
            "lecon",
            re.compile(
                r"^(?:LE[CÇ]ON|S[ÉE]QUENCE|TH[ÈE]ME)\s*"
                r"([0-9IVXLCDM]*)\s*[:.\-–—)]*\s*(.*)$",
                re.IGNORECASE,
            ),
        ),
        (
            "objectif",
            re.compile(
                r"^(OBJECTIFS? P[ÉE]DAGOGIQUES?|COMP[ÉE]TENCES ATTENDUES?)"
                r"\s*[:\-–—]?\s*(.*)$",
                re.IGNORECASE,
            ),
        ),
    )
    for type_element, motif in motifs:
        match = motif.match(ligne)
        if match:
            numero = (match.group(1) or "").strip()
            titre = _nettoyer_ligne(match.group(2) or "")
            if not titre:
                titre = _nettoyer_ligne(match.group(1) or type_element.title())
                numero = ""
            code = numero or str(type_element)
            return type_element, code, titre[:240]

    numerote = re.match(r"^(\d+(?:\.\d+){0,2})[.)\-]?\s+(.{3,220})$", ligne)
    if numerote:
        numero, titre = numerote.groups()
        type_element = "lecon" if numero.count(".") <= 1 else "rubrique"
        return type_element, numero, _nettoyer_ligne(titre)[:240]
    return None


def proposer_structure_programme(texte: str) -> list[dict[str, object]]:
    """Propose des chapitres/leçons sans les certifier.

    Les couvertures et titres préliminaires sont ignorés si un plan explicite
    existe. Sans plan détectable, le document reste un bloc à organiser.
    """
    lignes = [_nettoyer_ligne(l) for l in (texte or "").splitlines()]
    lignes = [l for l in lignes if l and not re.fullmatch(r"(?:page\s*)?\d{1,4}", l, re.I)]
    if not lignes:
        return []

    positions = [
        index for index, ligne in enumerate(lignes)
        if _identifier_titre(ligne) is not None
    ]
    if not positions:
        return [{
            "code": "DOC-1",
            "type_element": "rubrique",
            "titre": "Contenu extrait — structure à organiser",
            "contenu": "\n".join(lignes)[:MAX_TEXTE_ELEMENT],
            "ordre": 1,
            "parent_code": None,
        }]

    # Les lignes antérieures au premier titre reconnu correspondent souvent
    # à la couverture, au nom du ministère ou à des en-têtes de pagination.
    lignes = lignes[positions[0]:]
    items: list[dict[str, object]] = []
    courant: dict[str, object] | None = None
    chapitre_code: str | None = None
    ordre = 0

    def finaliser() -> None:
        if courant is None:
            return
        courant["contenu"] = str(courant.get("contenu", ""))[:MAX_TEXTE_ELEMENT]
        items.append(courant.copy())

    for ligne in lignes:
        titre = _identifier_titre(ligne)
        if titre:
            finaliser()
            type_element, numero, libelle = titre
            ordre += 1
            code = f"{type_element[:3].upper()}-{numero or ordre}-{ordre}"
            parent_code = (
                chapitre_code
                if type_element in {"lecon", "rubrique", "objectif"}
                else None
            )
            courant = {
                "code": code[:60],
                "type_element": type_element,
                "titre": libelle or f"{type_element.title()} {ordre}",
                "contenu": "",
                "ordre": ordre,
                "parent_code": parent_code,
            }
            if type_element == "chapitre":
                chapitre_code = code[:60]
            continue

        if courant is not None:
            ancien = str(courant.get("contenu", ""))
            courant["contenu"] = (ancien + "\n" + ligne).strip()[:MAX_TEXTE_ELEMENT]

    finaliser()
    return items[:MAX_ELEMENTS_PROPOSES]


def normaliser_code_element(titre: str, suffixe: int) -> str:
    """Crée un code court et ASCII, non dépendant des accents."""
    brut = unicodedata.normalize("NFKD", titre or "")
    ascii_titre = brut.encode("ascii", "ignore").decode("ascii").upper()
    slug = re.sub(r"[^A-Z0-9]+", "-", ascii_titre).strip("-")[:38] or "ELEMENT"
    return f"MAN-{slug}-{suffixe}"[:60]
