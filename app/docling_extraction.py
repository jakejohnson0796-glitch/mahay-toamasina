"""Adaptateur Docling optionnel pour les PDF scolaires et universitaires.

Docling n'est jamais importé au démarrage du site. Il est chargé à la demande,
uniquement lorsque DOCLING_ENABLED=true et que la dépendance optionnelle est
installée. Les conversions sont sérialisées pour éviter de charger plusieurs
pipelines/modèles simultanément sur une petite instance.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from threading import RLock

from .config import parametres

logger = logging.getLogger(__name__)
_CONVERSION_LOCK = RLock()


def _repertoire_modeles_docling() -> Path | None:
    valeur = str(getattr(parametres, "docling_artifacts_path", "") or "").strip()
    if not valeur:
        return None
    repertoire = Path(valeur).expanduser()
    if not repertoire.is_dir():
        return None
    try:
        return repertoire if any(repertoire.iterdir()) else None
    except OSError:
        return None


def docling_actif() -> bool:
    """Docling requiert un cache de modèles préparé hors du service web."""
    return bool(
        getattr(parametres, "docling_enabled", False)
        and _repertoire_modeles_docling() is not None
    )


@lru_cache(maxsize=1)
def _convertisseur_docling():
    """Construit un seul convertisseur PDF, à la première demande."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        TesseractCliOcrOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    repertoire_modeles = _repertoire_modeles_docling()
    if repertoire_modeles is None:
        raise RuntimeError("Cache des modèles Docling absent ou vide.")

    options = PdfPipelineOptions(
        artifacts_path=str(repertoire_modeles),
        do_ocr=True,
        do_table_structure=bool(
            getattr(parametres, "docling_table_structure", False)
        ),
        document_timeout=90,
        enable_remote_services=False,
        allow_external_plugins=False,
        generate_page_images=False,
        generate_picture_images=False,
        ocr_batch_size=1,
        layout_batch_size=1,
        table_batch_size=1,
        queue_max_size=2,
    )
    # Réutilise le Tesseract déjà présent dans l'image Docker. Pas de modèle
    # OCR téléchargé à la volée et pas de service distant.
    options.ocr_options = TesseractCliOcrOptions(
        lang=["fra", "eng"],
        scale=2.0,
    )
    # Réduit le nombre de threads d'inférence sur les instances CPU modestes.
    try:
        options.accelerator_options.num_threads = 2
    except (AttributeError, TypeError, ValueError):
        logger.debug("Le réglage du nombre de threads Docling est indisponible.")

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=options)
        }
    )


def extraire_pdf_docling(chemin: str | Path, max_caracteres: int) -> str:
    """Convertit un PDF en Markdown structuré, ou renvoie une chaîne vide.

    Les erreurs, timeouts et conversions sans texte exploitable sont délégués
    au moteur historique pdfplumber/Tesseract par l'appelant.
    """
    if not docling_actif():
        return ""

    try:
        with _CONVERSION_LOCK:
            resultat = _convertisseur_docling().convert(str(chemin))
            document = getattr(resultat, "document", None)
            if document is None:
                return ""

            has_timeout_errors = getattr(resultat, "has_timeout_errors", None)
            if callable(has_timeout_errors) and has_timeout_errors():
                logger.warning("Conversion Docling interrompue par son timeout.")
                return ""

            statut = str(getattr(resultat, "status", "")).lower()
            if "failure" in statut:
                return ""

            markdown = document.export_to_markdown()
            if not isinstance(markdown, str):
                return ""
            return markdown.strip()[:max(1, int(max_caracteres))]
    except ImportError:
        logger.warning(
            "DOCLING_ENABLED est actif mais le paquet Docling n'est pas installé."
        )
    except Exception as erreur:
        logger.warning(
            "Docling indisponible pour ce PDF (%s); repli vers l'extracteur classique.",
            type(erreur).__name__,
        )
    return ""
