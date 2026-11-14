import asyncio
import threading
from types import SimpleNamespace

from app.routers import documents_router
from app.upload_validation import valider_upload


class FichierTest:
    filename = "annale.pdf"

    def __init__(self, contenu=b"%PDF-1.7 fichier de test"):
        self.contenu = contenu

    async def read(self, taille):
        return self.contenu[:taille]


def _request_test():
    return SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={},
    )


def _preparer_route(monkeypatch, analyse):
    utilisateur = SimpleNamespace(id=42)
    monkeypatch.setattr(
        documents_router,
        "utilisateur_courant",
        lambda _request, _session: utilisateur,
    )
    monkeypatch.setattr(documents_router, "limite_depassee", lambda *_a, **_k: False)
    monkeypatch.setattr(documents_router, "_analyser_document_detection", analyse)


def test_detection_refuse_un_faux_pdf_avant_le_traitement(monkeypatch):
    appele = False

    def analyse(_contenu, _nom):
        nonlocal appele
        appele = True
        documents_router._DETECTION_DOCUMENT_SEMAPHORE.release()
        return {}

    _preparer_route(monkeypatch, analyse)
    response = asyncio.run(
        documents_router.detect_document_automatique(
            _request_test(), FichierTest(b"<html>ceci n'est pas un PDF</html>"), object()
        )
    )

    assert response.status_code == 400
    assert appele is False
    assert documents_router._DETECTION_DOCUMENT_SEMAPHORE.acquire(blocking=False) is True
    documents_router._DETECTION_DOCUMENT_SEMAPHORE.release()


def test_detection_ocr_est_deplacee_hors_de_la_boucle_http(monkeypatch):
    thread_ids = []

    def analyse(_contenu, _nom):
        try:
            thread_ids.append(threading.get_ident())
            return {"titre": "Annale de test"}
        finally:
            documents_router._DETECTION_DOCUMENT_SEMAPHORE.release()

    _preparer_route(monkeypatch, analyse)
    thread_principal = threading.get_ident()
    response = asyncio.run(
        documents_router.detect_document_automatique(
            _request_test(), FichierTest(), object()
        )
    )

    assert response.status_code == 200
    assert response.body
    assert thread_ids and thread_ids[0] != thread_principal


def test_detection_refuse_une_seconde_analyse_lorsque_le_slot_est_occupe(monkeypatch):
    def analyse(_contenu, _nom):
        documents_router._DETECTION_DOCUMENT_SEMAPHORE.release()
        return {}

    _preparer_route(monkeypatch, analyse)
    assert documents_router._DETECTION_DOCUMENT_SEMAPHORE.acquire(blocking=False) is True
    try:
        response = asyncio.run(
            documents_router.detect_document_automatique(
                _request_test(), FichierTest(), object()
            )
        )
        assert response.status_code == 429
        assert response.headers.get("retry-after") == "15"
    finally:
        documents_router._DETECTION_DOCUMENT_SEMAPHORE.release()


def test_validateur_de_detection_refuse_les_fichiers_avec_extension_fausse():
    import pytest

    with pytest.raises(ValueError):
        valider_upload(
            b"<html>pas un pdf</html>",
            "annale.pdf",
            20 * 1024 * 1024,
            {".pdf"},
        )


def test_detection_retourne_429_quand_le_moteur_global_est_sature(monkeypatch):
    from app.text_extraction import ExtractionSaturee

    def analyse(_contenu, _nom):
        try:
            raise ExtractionSaturee("Le moteur de lecture est occupé.")
        finally:
            documents_router._DETECTION_DOCUMENT_SEMAPHORE.release()

    _preparer_route(monkeypatch, analyse)
    response = asyncio.run(
        documents_router.detect_document_automatique(
            _request_test(), FichierTest(), object()
        )
    )
    assert response.status_code == 429
    assert response.headers.get("retry-after") == "15"
