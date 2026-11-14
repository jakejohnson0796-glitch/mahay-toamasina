"""
Extraction du texte d'un document depose, pour l'envoyer ensuite au
generateur de quiz IA (app/ai_quiz.py). C'etait le premier TODO de la V1 :
"il faut extraire le vrai texte du fichier avant de l'envoyer au generateur
de quiz" — c'est fait ici.

Deux strategies, appliquees dans l'ordre :
1. PDF avec du texte selectionnable -> pdfplumber (rapide, 100% Python,
   pas de dependance systeme).
2. Scan/image et PDF mêlant texte et images -> OCR via pytesseract.
   En production Docker, Tesseract français et anglais ainsi que Poppler sont
   installés. Si ces dépendances système manquent en développement local,
   l'extraction retombe sur le texte disponible sans faire planter l'appli.
"""
from dataclasses import dataclass
import logging
from pathlib import Path
import shutil
import subprocess
from threading import BoundedSemaphore

import pdfplumber

logger = logging.getLogger(__name__)

SEUIL_CARACTERES_PDF_TEXTE = 100  # en dessous de ca, on suppose que c'est un scan
MAX_PAGES_PDF_TEXTE = 60
MAX_PAGES_PDF_OCR = 15
MAX_TEXTE_EXTRAIT = 300_000
MAX_OCR_DPI = 160
MAX_PIXELS_IMAGE_OCR = 40_000_000
MAX_EXTRACTIONS_SIMULTANEES = 2
_SEMAPHORE_EXTRACTION = BoundedSemaphore(MAX_EXTRACTIONS_SIMULTANEES)


class ExtractionSaturee(RuntimeError):
    """Le moteur de lecture de documents atteint sa capacité sûre."""


def _acquerir_slot_extraction() -> None:
    if not _SEMAPHORE_EXTRACTION.acquire(blocking=False):
        raise ExtractionSaturee(
            "Le moteur de lecture est occupé. Réessayez dans quelques instants."
        )


def _extraire_texte_sans_limite_legacy(chemin_fichier: str) -> str:
    """Renvoie le texte du document, ou une chaine vide si l'extraction
    echoue completement (l'appelant doit gerer ce cas, voir ai_quiz.py)."""
    chemin = Path(chemin_fichier)
    suffixe = chemin.suffix.lower()

    if suffixe == ".pdf":
        # Extraction hybride page par page : un PDF peut mêler pages
        # sélectionnables et pages scannées. On OCR uniquement les pages
        # pauvres en texte au lieu de désactiver l'OCR dès qu'une couverture
        # contient quelques lignes sélectionnables.
        return _extraire_texte_pdf_legacy(chemin)

    if suffixe in (".docx",):
        return _extraire_texte_docx(chemin)

    if suffixe in (".pptx",):
        return _extraire_texte_pptx(chemin)

    if suffixe == ".doc":
        return _extraire_texte_bureautique_ancien(chemin, "antiword")

    if suffixe == ".ppt":
        return _extraire_texte_bureautique_ancien(chemin, "catppt")

    if suffixe in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"):
        return _extraire_texte_image(chemin)

    return ""



@dataclass(frozen=True)
class ResultatExtraction:
    """Texte extrait et moteur effectivement utilisé pour ce fichier."""

    texte: str
    moteur: str


def _texte_docling_utilisable(texte: str) -> bool:
    """Filtre prudent : un résultat vide/bruité repart vers l'ancien OCR."""
    texte = (texte or "").strip()
    if len(texte) < 120:
        return False
    visibles = [caractere for caractere in texte if not caractere.isspace()]
    if not visibles:
        return False
    alphanumeriques = sum(caractere.isalnum() for caractere in visibles)
    taux_alphanumerique = alphanumeriques / len(visibles)
    taux_remplacement = texte.count("\ufffd") / max(1, len(texte))
    return alphanumeriques >= 50 and taux_alphanumerique >= 0.18 and taux_remplacement <= 0.01


def _extraire_texte_detaille_sans_limite(chemin_fichier: str) -> ResultatExtraction:
    """Extrait le texte et décrit le moteur, sans exposer le contenu dans les logs."""
    chemin = Path(chemin_fichier)
    suffixe = chemin.suffix.lower()

    if suffixe == ".pdf":
        # Docling est réservé aux PDF de taille raisonnable. On garde le plafond
        # historique de pages avant de démarrer un pipeline de modèles.
        try:
            with pdfplumber.open(chemin) as pdf:
                nombre_pages = len(pdf.pages)
        except Exception:
            nombre_pages = MAX_PAGES_PDF_TEXTE + 1

        if nombre_pages <= MAX_PAGES_PDF_TEXTE:
            try:
                from .docling_extraction import docling_actif, extraire_pdf_docling

                if docling_actif():
                    texte_docling = extraire_pdf_docling(
                        chemin,
                        max_caracteres=MAX_TEXTE_EXTRAIT,
                    )
                    if _texte_docling_utilisable(texte_docling):
                        return ResultatExtraction(
                            texte=texte_docling[:MAX_TEXTE_EXTRAIT],
                            moteur="Docling (OCR intégré si nécessaire)",
                        )
            except Exception as erreur:
                # Une dépendance facultative ne doit jamais casser le dépôt.
                logger.warning(
                    "Repli extracteur PDF classique (%s).",
                    type(erreur).__name__,
                )

        return ResultatExtraction(
            texte=_extraire_texte_pdf_legacy(chemin),
            moteur="pdfplumber + Tesseract",
        )

    texte = _extraire_texte_sans_limite_legacy(str(chemin))
    if suffixe == ".docx":
        moteur = "python-docx"
    elif suffixe == ".pptx":
        moteur = "python-pptx"
    elif suffixe in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}:
        moteur = "Tesseract OCR"
    elif suffixe == ".doc":
        moteur = "antiword"
    elif suffixe == ".ppt":
        moteur = "catppt"
    else:
        moteur = "extracteur classique"
    return ResultatExtraction(texte=texte, moteur=moteur)


def _extraire_texte_sans_limite(chemin_fichier: str) -> str:
    """Compatibilité avec les anciens appelants qui attendent une chaîne."""
    return _extraire_texte_detaille_sans_limite(chemin_fichier).texte

def _extraire_passages_sans_limite(chemin_fichier: str) -> list[dict[str, str]]:
    """Extrait des passages avec un repère de provenance exploitable par le Tuteur.

    Les PDF textuels gardent leur numéro de page et les présentations leur
    numéro de diapositive. Les formats sans pagination fiable utilisent un
    repère explicite plutôt que de fabriquer des numéros de page.
    """
    chemin = Path(chemin_fichier)
    suffixe = chemin.suffix.lower()

    if suffixe == ".pdf":
        passages = []
        try:
            with pdfplumber.open(chemin) as pdf:
                total = 0
                for numero, page in enumerate(pdf.pages[:MAX_PAGES_PDF_TEXTE], start=1):
                    texte = (page.extract_text() or "").strip()
                    if texte:
                        passages.append({"reference": f"page {numero}", "texte": texte})
                        total += len(texte)
                    if total >= MAX_TEXTE_EXTRAIT:
                        break
        except Exception:
            return []
        return passages

    if suffixe == ".pptx":
        try:
            from pptx import Presentation

            presentation = Presentation(str(chemin))
            passages = []
            total = 0
            for numero, diapositive in enumerate(presentation.slides, start=1):
                if numero > 500 or total >= MAX_TEXTE_EXTRAIT:
                    break
                morceaux = []
                for forme in diapositive.shapes:
                    texte = getattr(forme, "text", "") or ""
                    if texte.strip():
                        morceaux.append(texte.strip())
                texte_diapositive = "\\n".join(morceaux).strip()
                if texte_diapositive:
                    texte_diapositive = texte_diapositive[:MAX_TEXTE_EXTRAIT - total]
                    passages.append({
                        "reference": f"diapositive {numero}",
                        "texte": texte_diapositive,
                    })
                    total += len(texte_diapositive)
            return passages
        except Exception:
            return []

    if suffixe == ".docx":
        try:
            from docx import Document as DocxDocument

            document = DocxDocument(str(chemin))
            passages = []
            total = 0
            for numero, paragraphe in enumerate(document.paragraphs, start=1):
                if numero > 2000 or total >= MAX_TEXTE_EXTRAIT:
                    break
                texte = (paragraphe.text or "").strip()
                if texte:
                    texte = texte[:MAX_TEXTE_EXTRAIT - total]
                    passages.append({
                        "reference": f"paragraphe {numero} (pagination indisponible)",
                        "texte": texte,
                    })
                    total += len(texte)
            if passages:
                return passages
        except Exception:
            return []

    # OCR, images et formats sans repères fiables : la source reste identifiée
    # par le document, sans inventer une page ou une diapositive.
    texte = _extraire_texte_sans_limite(str(chemin)).strip()
    if texte:
        return [{
            "reference": "document (pagination indisponible)",
            "texte": texte[:MAX_TEXTE_EXTRAIT],
        }]
    return []


def _extraire_texte_pdf_legacy(chemin: Path) -> str:
    morceaux = []
    nombre_pages_ocr = 0
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        pytesseract = None
        convert_from_path = None

    try:
        with pdfplumber.open(chemin) as pdf:
            total = 0
            for numero, page in enumerate(pdf.pages[:MAX_PAGES_PDF_TEXTE], start=1):
                morceau = (page.extract_text() or "").strip()
                if (
                    len(morceau) < SEUIL_CARACTERES_PDF_TEXTE
                    and pytesseract is not None
                    and convert_from_path is not None
                    and nombre_pages_ocr < MAX_PAGES_PDF_OCR
                ):
                    try:
                        images = convert_from_path(
                            str(chemin),
                            first_page=numero,
                            last_page=numero,
                            dpi=MAX_OCR_DPI,
                            thread_count=1,
                            use_pdftocairo=True,
                        )
                        if images:
                            try:
                                morceau_ocr = _ocr_image(images[0], pytesseract)
                                if len(morceau_ocr) > len(morceau):
                                    morceau = morceau_ocr
                            finally:
                                # Une seule page est rendue par itération :
                                # libère immédiatement ses pixels après l'OCR.
                                for image_rendue in images:
                                    try:
                                        image_rendue.close()
                                    except Exception:
                                        pass
                        nombre_pages_ocr += 1
                    except Exception:
                        # Une page endommagée ne doit pas empêcher la lecture
                        # des autres pages du même document.
                        nombre_pages_ocr += 1
                if morceau:
                    morceaux.append(morceau)
                    total += len(morceau)
                if total >= MAX_TEXTE_EXTRAIT:
                    break
    except Exception:
        return ""
    return "\n".join(morceaux)[:MAX_TEXTE_EXTRAIT]


def _langue_tesseract(pytesseract) -> str:
    """Choisit les modèles installés sans échouer si un modèle facultatif manque."""
    try:
        disponibles = set(pytesseract.get_languages(config=""))
    except Exception:
        disponibles = {"fra"}
    langues = [langue for langue in ("fra", "eng") if langue in disponibles]
    return "+".join(langues) or "eng"


def _preparer_image_ocr(image):
    """Améliore le contraste et la lisibilité des scans avant l'OCR."""
    from PIL import Image, ImageFilter, ImageOps

    largeur, hauteur = image.size
    if largeur <= 0 or hauteur <= 0 or largeur * hauteur > MAX_PIXELS_IMAGE_OCR:
        raise ValueError("Image trop grande pour l'OCR")
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB") if image.mode not in {"RGB", "L"} else image.copy()
    image = ImageOps.grayscale(image)
    image = ImageOps.autocontrast(image, cutoff=1)
    plus_grand_cote = max(image.size)
    if 0 < plus_grand_cote < 1800:
        facteur = min(1.8, 1800 / plus_grand_cote)
        image = image.resize(
            (max(1, int(image.width * facteur)), max(1, int(image.height * facteur))),
            Image.Resampling.LANCZOS,
        )
    return image.filter(ImageFilter.SHARPEN)


def _ocr_image(image, pytesseract) -> str:
    image_preparee = _preparer_image_ocr(image)
    return (pytesseract.image_to_string(
        image_preparee,
        lang=_langue_tesseract(pytesseract),
        config="--oem 1 --psm 3 -c preserve_interword_spaces=1",
        timeout=25,
    ) or "").strip()


def _extraire_texte_pdf_par_ocr(chemin: Path) -> str:
    """OCR borné des PDF scannés, avec prétraitement et modèles FR/EN."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        return ""
    try:
        pages = convert_from_path(
            str(chemin),
            first_page=1,
            last_page=MAX_PAGES_PDF_OCR,
            dpi=MAX_OCR_DPI,
            thread_count=1,
            use_pdftocairo=True,
        )
        morceaux = []
        total = 0
        for page in pages:
            morceau = _ocr_image(page, pytesseract)
            morceaux.append(morceau)
            total += len(morceau)
            if total >= MAX_TEXTE_EXTRAIT:
                break
        return "\n".join(morceaux)[:MAX_TEXTE_EXTRAIT]
    except Exception:
        return ""


def _extraire_texte_image(chemin: Path) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""
    try:
        with Image.open(chemin) as image:
            return _ocr_image(image, pytesseract)[:MAX_TEXTE_EXTRAIT]
    except Exception:
        return ""


def _extraire_texte_bureautique_ancien(chemin: Path, executable: str) -> str:
    """Lit les anciens formats .doc/.ppt avec antiword/catppt si présents."""
    commande = shutil.which(executable)
    if not commande:
        return ""
    try:
        resultat = subprocess.run(
            [commande, str(chemin)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
            check=False,
        )
        if resultat.returncode != 0:
            return ""
        return (resultat.stdout or "")[:MAX_TEXTE_EXTRAIT]
    except (OSError, subprocess.SubprocessError):
        return ""


def _extraire_texte_docx(chemin: Path) -> str:
    try:
        from docx import Document as DocxDocument
    except ImportError:
        return ""
    try:
        document = DocxDocument(str(chemin))
        morceaux = [p.text.strip() for p in document.paragraphs if p.text.strip()]
        # Les supports de cours et tableaux de résultats contiennent souvent
        # la matière et les dates uniquement dans les cellules des tableaux.
        for tableau in document.tables:
            for ligne in tableau.rows:
                cellules = [cellule.text.strip() for cellule in ligne.cells if cellule.text.strip()]
                if cellules:
                    morceaux.append(" | ".join(cellules))
        for section in document.sections:
            for zone in (section.header, section.footer):
                morceaux.extend(
                    p.text.strip() for p in zone.paragraphs if p.text.strip()
                )
        return "\n".join(morceaux)[:MAX_TEXTE_EXTRAIT]
    except Exception:
        return ""


def _extraire_texte_pptx(chemin: Path) -> str:
    try:
        from pptx import Presentation
    except ImportError:
        return ""
    try:
        presentation = Presentation(str(chemin))
        morceaux = []
        total = 0
        for slide in presentation.slides:
            for shape in slide.shapes:
                texte = getattr(shape, "text", "") or ""
                if texte.strip():
                    morceaux.append(texte)
                    total += len(texte)
                    if total >= MAX_TEXTE_EXTRAIT:
                        return "\n".join(morceaux)[:MAX_TEXTE_EXTRAIT]
        return "\n".join(morceaux)[:MAX_TEXTE_EXTRAIT]
    except Exception:
        return ""


def extraire_texte_detaille(chemin_fichier: str) -> ResultatExtraction:
    """Extraction détaillée sous le même plafond global que l'OCR."""
    _acquerir_slot_extraction()
    try:
        return _extraire_texte_detaille_sans_limite(chemin_fichier)
    finally:
        _SEMAPHORE_EXTRACTION.release()


def extraire_texte(chemin_fichier: str) -> str:
    """API historique conservée pour les appels qui ne demandent que le texte."""
    return extraire_texte_detaille(chemin_fichier).texte


def extraire_passages_avec_sources(chemin_fichier: str) -> list[dict[str, str]]:
    """Extraction avec sources, sous le même plafond global que l'OCR."""
    _acquerir_slot_extraction()
    try:
        return _extraire_passages_sans_limite(chemin_fichier)
    finally:
        _SEMAPHORE_EXTRACTION.release()
