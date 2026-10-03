from pathlib import Path


def test_formulaire_auto_ne_force_pas_des_metadonnees_par_defaut():
    contenu = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "templates"
        / "document_upload.html"
    ).read_text(encoding="utf-8")

    assert 'placeholder="Ex. 2026"' in contenu
    assert 'value="2026"' not in contenu
    assert '<option value="">Choisir le type de document</option>' in contenu
    assert 'Choisir une filière — la détection automatique peut la proposer' in contenu


def test_formulaire_declenche_une_detection_live():
    contenu = (
        Path(__file__).resolve().parents[1] / "app" / "templates" / "document_upload.html"
    ).read_text(encoding="utf-8")
    assert 'fetch("/documents/detect"' in contenu
    assert "Détection automatique en cours" in contenu


def test_route_detection_automatique_existe():
    from app.routers.documents_router import detect_document_automatique
    assert detect_document_automatique.__annotations__["fichier"] is not None
