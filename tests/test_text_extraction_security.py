import pytest

from app import text_extraction


def test_ocr_et_extraction_partagent_un_plafond_global(monkeypatch):
    semaphore = text_extraction._SEMAPHORE_EXTRACTION
    assert semaphore.acquire(blocking=False) is True
    try:
        with pytest.raises(text_extraction.ExtractionSaturee):
            text_extraction.extraire_texte("annale.pdf")
        with pytest.raises(text_extraction.ExtractionSaturee):
            text_extraction.extraire_passages_avec_sources("annale.pdf")
    finally:
        semaphore.release()


def test_extraction_saturee_est_un_signal_explicitement_identifiable():
    assert issubclass(text_extraction.ExtractionSaturee, RuntimeError)
    assert text_extraction.MAX_EXTRACTIONS_SIMULTANEES == 2
