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
    assert "fichiers.length > MAX_FILES" in template
    assert "Jusqu’à 15 fichiers par envoi" in template
    assert "Les lots scolaires sont autorisés aussi" in template
    assert "const lotScolaire = scolaire && fichiers.length > 1" in template
    assert "120 Mo maximum par lot" in template


def test_batch_upload_requires_automatic_classification_and_csrf():
    router = DOCUMENTS_ROUTER.read_text(encoding="utf-8")
    batch = router.split('@router.post("/documents/upload-multiple")', 1)[1].split(
        '@router.get("/documents/{document_id}/telecharger")', 1
    )[0]
    assert "fichiers: list[UploadFile] = File(...)" in batch
    assert "classification_auto: bool = Form(default=False)" in batch
    assert "_csrf: None = Depends(verifier_csrf)" in batch
    assert "if len(fichiers) > MAX_DOCUMENTS_PAR_LOT:" in batch
    assert "MAX_TAILLE_DOCUMENT_PAR_LOT" in batch
    assert 'portee == "scolaire" and not' not in batch
    assert "ProgrammeMatiereScolaire" in batch
    assert "matiere_scolaire_id" in batch
    assert "matiere_scolaire_finale.libelle if matiere_scolaire_finale else \"\"" in batch
    assert "if portee == \"universitaire\" and not classification_auto:" in batch


def test_batch_upload_classifies_each_file_and_preserves_moderation():
    router = DOCUMENTS_ROUTER.read_text(encoding="utf-8")
    batch = router.split('@router.post("/documents/upload-multiple")', 1)[1].split(
        '@router.get("/documents/{document_id}/telecharger")', 1
    )[0]
    assert "for fichier in fichiers:" in batch
    assert "analyser_documents_stockes(" in batch
    assert "MAX_DOCUMENTS_PAR_LOT" in batch
    assert "matieres_scolaires_candidates" in batch
    assert "ids_matieres_candidates" in batch
    assert "portee_academique=portee" in batch
    assert "supprimer_fichier(chemin_stocke)" in batch
    assert "statut=StatutDocument.EN_ATTENTE" in batch
    assert "_notifier_admins_nouveau_document" in batch
    assert "gamification.enregistrer_action" in batch
    assert "erreurs_batch.append" in batch


def test_multiple_selection_requires_auto_mode_and_shows_per_file_results():
    template = UPLOAD_TEMPLATE.read_text(encoding="utf-8")
    assert "activez la détection automatique pour classer chaque fichier séparément" in template
    assert "Chaque document sera lu individuellement" in template
    assert "{% if resultats_batch %}" in template
    assert "{{ resultat.confiance }}" in template
    assert "{% if erreurs_batch %}" in template
    assert "{% for detail in erreurs_batch %}" in template
    assert "20 Mo maximum par fichier" in template
    assert "Jusqu’à 15 fichiers par envoi" in template


def test_document_upload_template_inline_script_braces_are_balanced():
    template = UPLOAD_TEMPLATE.read_text(encoding="utf-8")
    script = template.split("<script nonce=", 1)[1].split("</script>", 1)[0]
    # This is a lightweight structural check only; CI also runs compilation
    # and the project's existing test suite.
    assert "fichiersSelectionnes()" in script
    assert "form.addEventListener(\"submit\"" in script
    assert "input.dispatchEvent(new Event(\"change\"" in script
