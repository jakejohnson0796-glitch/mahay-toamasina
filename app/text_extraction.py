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
import subprocess
import tempfile

import pdfplumber

SEUIL_CARACTERES_PDF_TEXTE = 100  # en dessous de ca, on suppose que c'est un scan
MAX_PAGES_PDF_TEXTE = 60
MAX_PAGES_PDF_OCR = 20
MAX_TEXTE_EXTRAIT = 300_000
MAX_OCR_DPI = 120


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

    if suffixe == ".doc":
        return _extraire_texte_legacy("antiword", chemin)

    if suffixe in (".docx",):
        return _extraire_texte_docx(chemin)

    if suffixe == ".ppt":
        return _extraire_texte_legacy("catppt", chemin)

    if suffixe in (".pptx",):
        return _extraire_texte_pptx(chemin)

    if suffixe in (".png", ".jpg", ".jpeg", ".webp"):
        return _extraire_texte_image(chemin)

    return ""


def extraire_passages_avec_sources(chemin_fichier: str) -> list[dict[str, str]]:
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
                texte_diapositive = "\n".join(morceaux).strip()
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
    texte = extraire_texte(str(chemin)).strip()
    if texte:
        return [{
            "reference": "document (pagination indisponible)",
            "texte": texte[:MAX_TEXTE_EXTRAIT],
        }]
    return []


def _extraire_texte_pdf(chemin: Path) -> str:
    morceaux = []
    try:
        with pdfplumber.open(chemin) as pdf:
            total = 0
            for page in pdf.pages[:MAX_PAGES_PDF_TEXTE]:
                morceau = page.extract_text() or ""
                morceaux.append(morceau)
                total += len(morceau)
                if total >= MAX_TEXTE_EXTRAIT:
                    break
    except Exception:
        return ""
    return "\n".join(morceaux)


def _extraire_texte_pdf_par_ocr(chemin: Path) -> str:
    """OCR borné page par page, sans conserver tout le PDF rendu en mémoire."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
        from PIL import Image
    except ImportError:
        return ""
    try:
        with tempfile.TemporaryDirectory(prefix="mitaridala-ocr-") as dossier:
            chemins_images = convert_from_path(
                str(chemin),
                first_page=1,
                last_page=MAX_PAGES_PDF_OCR,
                dpi=150,
                use_pdftocairo=True,
                output_folder=dossier,
                paths_only=True,
                thread_count=1,
            )
            morceaux = []
            total = 0
            for chemin_image in chemins_images:
                with Image.open(chemin_image) as image:
                    morceau = _ocr_image(image, pytesseract)
                if morceau.strip():
                    morceaux.append(morceau)
                    total += len(morceau)
                if total >= MAX_TEXTE_EXTRAIT:
                    break
            return "\n".join(morceaux)[:MAX_TEXTE_EXTRAIT]
    except Exception:
        return ""


def _ocr_image(image, pytesseract_module=None) -> str:
    """Corrige l'orientation et le contraste avant l'OCR français/anglais."""
    try:
        from PIL import ImageOps
        if pytesseract_module is None:
            import pytesseract as pytesseract_module
        image = ImageOps.exif_transpose(image)
        image = ImageOps.grayscale(image)
        image = ImageOps.autocontrast(image)
        largeur, hauteur = image.size
        if largeur > 3600:
            facteur = 3600 / largeur
            image = image.resize((3600, max(1, int(hauteur * facteur))))
        try:
            return pytesseract_module.image_to_string(
                image, lang="fra+eng", config="--psm 6", timeout=25
            )[:MAX_TEXTE_EXTRAIT]
        except Exception:
            try:
                return pytesseract_module.image_to_string(
                    image, lang="eng", config="--psm 6", timeout=25
                )[:MAX_TEXTE_EXTRAIT]
            except Exception:
                return ""
    except Exception:
        return ""


def _extraire_texte_image(chemin: Path) -> str:
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        return ""
    try:
        with Image.open(chemin) as image:
            return _ocr_image(image, pytesseract)
    except Exception:
        return ""


def _extraire_texte_docx(chemin: Path) -> str:
    try:
        from docx import Document as DocxDocument
    except ImportError:
        return ""
    try:
        document = DocxDocument(str(chemin))
        morceaux = []
        total = 0

        def ajouter(valeur: str) -> None:
            nonlocal total
            texte = (valeur or "").strip()
            if texte and total < MAX_TEXTE_EXTRAIT:
                texte = texte[:MAX_TEXTE_EXTRAIT - total]
                morceaux.append(texte)
                total += len(texte)

        for paragraphe in document.paragraphs:
            ajouter(paragraphe.text)
        for table in document.tables:
            for ligne in table.rows:
                ajouter(" | ".join(cellule.text for cellule in ligne.cells))
        for section in document.sections:
            for zone in (section.header, section.footer):
                for paragraphe in zone.paragraphs:
                    ajouter(paragraphe.text)
                for table in zone.tables:
                    for ligne in table.rows:
                        ajouter(" | ".join(cellule.text for cellule in ligne.cells))
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
        for numero, diapositive in enumerate(presentation.slides, start=1):
            if numero > 500 or total >= MAX_TEXTE_EXTRAIT:
                break
            morceaux_diapo = []
            for forme in diapositive.shapes:
                texte = getattr(forme, "text", "") or ""
                if texte.strip():
                    morceaux_diapo.append(texte.strip())
                if getattr(forme, "has_table", False):
                    for ligne in forme.table.rows:
                        cellules = [cellule.text.strip() for cellule in ligne.cells]
                        if any(cellules):
                            morceaux_diapo.append(" | ".join(cellules))
            contenu_diapo = "\n".join(morceaux_diapo).strip()
            if contenu_diapo:
                contenu_diapo = contenu_diapo[:MAX_TEXTE_EXTRAIT - total]
                morceaux.append(f"Diapositive {numero}\n{contenu_diapo}")
                total += len(contenu_diapo)
        return "\n".join(morceaux)[:MAX_TEXTE_EXTRAIT]
    except Exception:
        return ""


def _extraire_texte_legacy(commande: str, chemin: Path) -> str:
    """Extrait les anciens fichiers Office sans lancer de shell."""
    try:
        resultat = subprocess.run(
            [commande, str(chemin)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
            check=False,
        )
        if resultat.returncode != 0:
            return ""
        return (resultat.stdout or "")[:MAX_TEXTE_EXTRAIT]
    except Exception:
        return ""
