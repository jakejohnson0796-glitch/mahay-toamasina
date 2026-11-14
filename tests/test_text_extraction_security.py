from threading import BoundedSemaphore

import pytest

from app import text_extraction


def test_ocr_et_extraction_partagent_un_plafond_global(monkeypatch):
    semaphore = BoundedSemaphore(text_extraction.MAX_EXTRACTIONS_SIMULTANEES)
    monkeypatch.setattr(text_extraction, "_SEMAPHORE_EXTRACTION", semaphore)

    places_occupees = [
        semaphore.acquire(blocking=False)
        for _ in range(text_extraction.MAX_EXTRACTIONS_SIMULTANEES)
    ]
    assert all(places_occupees)

    try:
        with pytest.raises(text_extraction.ExtractionSaturee):
            text_extraction.extraire_texte("annale.pdf")
        with pytest.raises(text_extraction.ExtractionSaturee):
            text_extraction.extraire_passages_avec_sources("annale.pdf")
    finally:
        for _ in places_occupees:
            semaphore.release()


def test_extraction_saturee_est_un_signal_explicitement_identifiable():
    assert issubclass(text_extraction.ExtractionSaturee, RuntimeError)
    assert text_extraction.MAX_EXTRACTIONS_SIMULTANEES == 2
