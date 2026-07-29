"""
Extraction du texte d'un document depose, pour l'envoyer ensuite au
generateur de quiz IA (app/ai_quiz.py). C'etait le premier TODO de la V1 :
"il faut extraire le vrai texte du fichier avant de l'envoyer au generateur
de quiz" — c'est fait ici.

Deux strategies, appliquees dans l'ordre :
1. PDF avec du texte selectionnable -> pdfplumber (rapide, 100% Python,
   pas de dependance systeme).
2. Scan/image, ou PDF ou pdfplumber ne sort presque rien -> OCR via
   pytesseract. Necessite le binaire Tesseract installe sur la machine
   (`apt install tesseract-ocr tesseract-ocr-fra` sous Linux, installeur
   officiel sous Windows) et, pour les PDF scannes, `poppler` pour
   pdf2image (`apt install poppler-utils`). C'est optionnel : si ces
   dependances manquent, l'extraction retombe simplement sur une chaine
   vide plutot que de faire planter l'appli.
"""
from pathlib import Path

import pdfplumber

SEUIL_CARACTERES_PDF_TEXTE = 100  # en dessous de ca, on suppose que c'est un scan


def extraire_texte(chemin_fichier: str) -> str:
    """Renvoie le texte du document, ou une chaine vide si l'extraction
    echoue completement (l'appelant doit gerer ce cas, voir ai_quiz.py)."""
    chemin = Path(chemin_fichier)
    suffixe = chemin.suffix.lower()

    if suffixe == ".pdf":
        texte = _extraire_texte_pdf(chemin)
        if len(texte.strip()) >= SEUIL_CARACTERES_PDF_TEXTE:
            return texte
        return _extraire_texte_pdf_par_ocr(chemin) or texte

    if suffixe in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"):
        return _extraire_texte_image(chemin)

    return ""


def _extraire_texte_pdf(chemin: Path) -> str:
    morceaux = []
    try:
        with pdfplumber.open(chemin) as pdf:
            for page in pdf.pages:
                morceaux.append(page.extract_text() or "")
    except Exception:
        return ""
    return "\n".join(morceaux)


def _extraire_texte_pdf_par_ocr(chemin: Path) -> str:
    """OCR page par page pour un PDF scanne (import local expres : voir
    le commentaire en tete de fichier sur les dependances optionnelles)."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        return ""
    try:
        pages = convert_from_path(str(chemin))
        return "\n".join(pytesseract.image_to_string(page, lang="fra") for page in pages)
    except Exception:
        return ""


def _extraire_texte_image(chemin: Path) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""
    try:
        return pytesseract.image_to_string(Image.open(chemin), lang="fra")
    except Exception:
        return ""
