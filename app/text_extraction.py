"""
Extraction du texte d'un document depose, pour l'envoyer ensuite au
generateur de quiz IA (app/ai_quiz.py). C'etait le premier TODO de la V1 :
"il faut extraire le vrai texte du fichier avant de l'envoyer au generateur
de quiz" — c'est fait ici.

Deux strategies, appliquees dans l'ordre :
1. PDF avec du texte selectionnable -> pdfplumber (rapide, 100% Python,
   pas de dependance systeme).
2. Scan/image et PDF mêlant texte et images -> PaddleOCR PP-OCRv5 français.
3. Si PaddleOCR est absent ou échoue, repli vers Tesseract français/anglais.
   Les deux moteurs OCR sont bornés en pages, taille et concurrence.
"""
from dataclasses import dataclass
import logging
from pathlib import Path
import shutil
import subprocess
from threading import BoundedSemaphore, RLock

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
_PADDLE_OCR_INIT_LOCK = RLock()
_PADDLE_OCR_INFERENCE_LOCK = RLock()
_PADDLE_OCR_INSTANCE = None
_PADDLE_OCR_ECHEC = False


class ExtractionSaturee(RuntimeError):
    """Le moteur de lecture de documents atteint sa capacité sûre."""


def _paddleocr_installe() -> bool:
    """Vérifie la présence du paquet et du runtime CPU sans les initialiser."""
    from importlib.util import find_spec

    try:
        return find_spec("paddleocr") is not None and find_spec("paddle") is not None
    except (ImportError, ValueError):
        return False


def _obtenir_moteur_paddleocr():
    """Charge une seule instance PaddleOCR à la première vraie page scannée."""
    global _PADDLE_OCR_INSTANCE, _PADDLE_OCR_ECHEC
    if _PADDLE_OCR_INSTANCE is not None:
        return _PADDLE_OCR_INSTANCE
    if _PADDLE_OCR_ECHEC:
        return None

    with _PADDLE_OCR_INIT_LOCK:
        if _PADDLE_OCR_INSTANCE is not None:
            return _PADDLE_OCR_INSTANCE
        if _PADDLE_OCR_ECHEC:
            return None
        try:
            from paddleocr import PaddleOCR

            _PADDLE_OCR_INSTANCE = PaddleOCR(
                lang="fr",
                ocr_version="PP-OCRv5",
                device="cpu",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except Exception as erreur:
            _PADDLE_OCR_ECHEC = True
            logger.warning(
                "PaddleOCR indisponible; repli Tesseract (%s).",
                type(erreur).__name__,
            )
            return None
    return _PADDLE_OCR_INSTANCE


def _textes_depuis_resultat_paddle(resultat) -> list[str]:
    """Normalise les sorties PaddleOCR 3.x et l'ancien format de lignes OCR."""
    import json

    donnees = getattr(resultat, "json", None)
    if callable(donnees):
        donnees = donnees()
    if donnees is None and isinstance(resultat, dict):
        donnees = resultat
    if isinstance(donnees, str):
        try:
            donnees = json.loads(donnees)
        except (TypeError, ValueError):
            donnees = None

    textes: list[str] = []
    if isinstance(donnees, dict):
        donnees = donnees.get("res", donnees)
        if isinstance(donnees, dict):
            rec_textes = donnees.get("rec_texts")
            rec_scores = donnees.get("rec_scores")
            if rec_textes is None:
                rec_textes = []
            elif isinstance(rec_textes, str):
                rec_textes = [rec_textes]
            else:
                try:
                    rec_textes = list(rec_textes)
                except TypeError:
                    rec_textes = []
            if rec_scores is None:
                rec_scores = []
            elif isinstance(rec_scores, (str, bytes)):
                rec_scores = [rec_scores]
            else:
                try:
                    rec_scores = list(rec_scores)
                except TypeError:
                    rec_scores = []
            for index, texte in enumerate(rec_textes):
                if not isinstance(texte, str) or not texte.strip():
                    continue
                score = rec_scores[index] if index < len(rec_scores) else 1.0
                try:
                    if float(score) < 0.25:
                        continue
                except (TypeError, ValueError):
                    pass
                textes.append(texte.strip())

    # Compatibilité avec le format legacy: [polygone, (texte, confiance)].
    if not textes and isinstance(resultat, (list, tuple)):
        lignes = resultat
        if lignes and isinstance(lignes[0], (list, tuple)) and len(lignes[0]) >= 2:
            candidat = lignes[0][1]
            if isinstance(candidat, (list, tuple)) and candidat and isinstance(candidat[0], str):
                for ligne in lignes:
                    if not isinstance(ligne, (list, tuple)) or len(ligne) < 2:
                        continue
                    candidat = ligne[1]
                    if not isinstance(candidat, (list, tuple)) or not candidat:
                        continue
                    texte = candidat[0]
                    score = candidat[1] if len(candidat) > 1 else 1.0
                    try:
                        if float(score) < 0.25:
                            continue
                    except (TypeError, ValueError):
                        pass
                    if isinstance(texte, str) and texte.strip():
                        textes.append(texte.strip())
    return textes


def _ocr_image_paddle(image) -> str:
    """Reconnaissance PP-OCRv5 sur CPU; ne télécharge les modèles qu'au besoin."""
    moteur = _obtenir_moteur_paddleocr()
    if moteur is None:
        return ""
    image_rgb = None
    try:
        import numpy as np

        image_rgb = image.convert("RGB")
        # PaddleX attend une image OpenCV (BGR) lorsqu'on lui transmet un ndarray.
        tableau = np.asarray(image_rgb)[:, :, ::-1].copy()
        with _PADDLE_OCR_INFERENCE_LOCK:
            resultats = moteur.predict(tableau)
        morceaux = []
        for resultat in resultats or []:
            morceaux.extend(_textes_depuis_resultat_paddle(resultat))
        return "\n".join(morceaux).strip()[:MAX_TEXTE_EXTRAIT]
    except Exception as erreur:
        logger.warning("Échec PaddleOCR; repli Tesseract (%s).", type(erreur).__name__)
        return ""
    finally:
        if image_rgb is not None:
            image_rgb.close()


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


def _pdf_contient_pages_scannes(chemin: Path) -> bool:
    """Détecte les pages pauvres en texte pour leur réserver le pipeline OCR."""
    try:
        with pdfplumber.open(chemin) as pdf:
            for page in pdf.pages[:MAX_PAGES_PDF_TEXTE]:
                extraire = getattr(page, "extract_text", None)
                # Les doubles de test ou extracteurs tiers sans API de page
                # ne doivent pas être assimilés à des scans.
                if not callable(extraire):
                    continue
                try:
                    if len((extraire() or "").strip()) < SEUIL_CARACTERES_PDF_TEXTE:
                        return True
                except Exception:
                    return True
    except Exception:
        return False
    return False


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

        if (
            nombre_pages <= MAX_PAGES_PDF_TEXTE
            and not _pdf_contient_pages_scannes(chemin)
        ):
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
            moteur="pdfplumber + PaddleOCR/Tesseract",
        )

    texte = _extraire_texte_sans_limite_legacy(str(chemin))
    if suffixe == ".docx":
        moteur = "python-docx"
    elif suffixe == ".pptx":
        moteur = "python-pptx"
    elif suffixe in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}:
        moteur = "PaddleOCR/Tesseract OCR"
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
        from pdf2image import convert_from_path
    except ImportError:
        convert_from_path = None
    try:
        import pytesseract
    except ImportError:
        pytesseract = None

    try:
        with pdfplumber.open(chemin) as pdf:
            total = 0
            for numero, page in enumerate(pdf.pages[:MAX_PAGES_PDF_TEXTE], start=1):
                morceau = (page.extract_text() or "").strip()
                if (
                    len(morceau) < SEUIL_CARACTERES_PDF_TEXTE
                    and convert_from_path is not None
                    and (pytesseract is not None or _paddleocr_installe())
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


def _extraire_texte_pdf(chemin: Path) -> str:
    """Alias de compatibilité pour les tests et anciens appelants internes."""
    return _extraire_texte_pdf_legacy(chemin)


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
    """PaddleOCR est prioritaire; Tesseract corrige les résultats absents/faibles."""
    image_preparee = _preparer_image_ocr(image)
    texte_paddle = _ocr_image_paddle(image_preparee)
    if len(texte_paddle) >= 30:
        return texte_paddle
    if pytesseract is None:
        return texte_paddle

    try:
        texte_tesseract = (pytesseract.image_to_string(
            image_preparee,
            lang=_langue_tesseract(pytesseract),
            config="--oem 1 --psm 3 -c preserve_interword_spaces=1",
            timeout=25,
        ) or "").strip()
    except Exception as erreur:
        logger.warning("Échec Tesseract OCR (%s).", type(erreur).__name__)
        return texte_paddle

    # Le repli n'écrase jamais un résultat PaddleOCR plus riche.
    return texte_tesseract if len(texte_tesseract) > len(texte_paddle) else texte_paddle


def _extraire_texte_pdf_par_ocr(chemin: Path) -> str:
    """OCR borné des PDF scannés, avec prétraitement et modèles FR/EN."""
    try:
        from pdf2image import convert_from_path
    except ImportError:
        return ""
    try:
        import pytesseract
    except ImportError:
        pytesseract = None
    if pytesseract is None and not _paddleocr_installe():
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
        from PIL import Image
    except ImportError:
        return ""
    try:
        import pytesseract
    except ImportError:
        pytesseract = None
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
