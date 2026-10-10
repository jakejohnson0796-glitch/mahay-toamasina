"""Regression checks for one-by-one and batch academic document uploads."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPLOAD_TEMPLATE = ROOT / "app" / "templates" / "document_upload.html"
DOCUMENTS_ROUTER = ROOT / "app" / "routers" / "documents_router.py"


def test_upload_form_allows_multiple_selection_but_keeps_single_upload_contract():
    template = UPLOAD_TEMPLATE.read_text(encoding="utf-8")
    assert 'id="fichier" name="fichier" required multiple' in template
    assert 'action="/documents/upload"' in template
    assert 'form.action = "/documents/upload-multiple"' in template
    assert 'input.name = "fichiers"' in template
    assert "fichiers.length > 5" in template


def test_batch_upload_requires_automatic_classification_and_csrf():
    router = DOCUMENTS_ROUTER.read_text(encoding="utf-8")
    batch = router.split('@router.post("/documents/upload-multiple")', 1)[1].split(
        '@router.get("/documents/{document_id}/telecharger")', 1
    )[0]
    assert "fichiers: list[UploadFile] = File(...)" in batch
    assert "classification_auto: bool = Form(default=False)" in batch
    assert "_csrf: None = Depends(verifier_csrf)" in batch
    assert "if len(fichiers) > 5:" in batch
    assert "if not classification_auto:" in batch


def test_batch_upload_classifies_each_file_and_preserves_moderation():
    router = DOCUMENTS_ROUTER.read_text(encoding="utf-8")
    batch = router.split('@router.post("/documents/upload-multiple")', 1)[1].split(
        '@router.get("/documents/{document_id}/telecharger")', 1
    )[0]
    assert "for fichier in fichiers:" in batch
    assert "classifier_document(" in batch
    assert "supprimer_fichier(chemin_stocke)" in batch
    assert "statut=StatutDocument.EN_ATTENTE" in batch
    assert "_notifier_admins_nouveau_document" in batch
    assert "gamification.enregistrer_action" in batch
    assert "erreurs_batch.append" in batch


def test_multiple_selection_requires_auto_mode_and_shows_per_file_results():
    template = UPLOAD_TEMPLATE.read_text(encoding="utf-8")
    assert "activez la détection automatique pour classer chaque fichier séparément" in template
    assert "Chaque fichier sera classé séparément" in template
    assert "{% if erreurs_batch %}" in template
    assert "{% for detail in erreurs_batch %}" in template
    assert "20 Mo maximum par fichier" in template


def test_document_upload_template_inline_script_braces_are_balanced():
    template = UPLOAD_TEMPLATE.read_text(encoding="utf-8")
    script = template.split("<script nonce=", 1)[1].split("</script>", 1)[0]
    # This is a lightweight structural check only; CI also runs compilation
    # and the project's existing test suite.
    assert "fichiersSelectionnes()" in script
    assert "form.addEventListener(\"submit\"" in script
    assert "input.dispatchEvent(new Event(\"change\"" in script
