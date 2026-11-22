from types import SimpleNamespace

from app import docling_extraction, text_extraction


def test_docling_reste_desactive_par_defaut(monkeypatch):
    monkeypatch.setattr(docling_extraction.parametres, "docling_enabled", False)
    assert docling_extraction.docling_actif() is False
    assert docling_extraction.extraire_pdf_docling("document.pdf", 1000) == ""


def test_docling_exige_un_cache_de_modeles_non_vide(monkeypatch, tmp_path):
    monkeypatch.setattr(docling_extraction.parametres, "docling_enabled", True)
    monkeypatch.setattr(
        docling_extraction.parametres, "docling_artifacts_path", str(tmp_path / "absent")
    )
    assert docling_extraction.docling_actif() is False

    cache = tmp_path / "models"
    cache.mkdir()
    (cache / "model.bin").write_bytes(b"weights")
    monkeypatch.setattr(docling_extraction.parametres, "docling_artifacts_path", str(cache))
    assert docling_extraction.docling_actif() is True


def test_adaptateur_docling_exporte_du_markdown(monkeypatch):
    texte_attendu = ("Titre du document\n\n" + "Contenu pédagogique structuré. " * 20).strip()

    class FauxConvertisseur:
        def convert(self, chemin):
            assert chemin == "annale.pdf"
            document = SimpleNamespace(export_to_markdown=lambda: texte_attendu)
            return SimpleNamespace(
                document=document,
                status="success",
                has_timeout_errors=lambda: False,
            )

    monkeypatch.setattr(docling_extraction, "docling_actif", lambda: True)
    monkeypatch.setattr(docling_extraction, "_convertisseur_docling", lambda: FauxConvertisseur())

    assert docling_extraction.extraire_pdf_docling("annale.pdf", 10000) == texte_attendu


def test_pdf_utilise_docling_quand_le_texte_est_exploitable(monkeypatch, tmp_path):
    chemin = tmp_path / "annale.pdf"
    chemin.write_bytes(b"%PDF-test")
    texte = "Sujet de mathématiques\n" + ("Analyse des fonctions et exercices. " * 30)

    monkeypatch.setattr("app.docling_extraction.docling_actif", lambda: True)
    monkeypatch.setattr("app.docling_extraction.extraire_pdf_docling", lambda *_a, **_k: texte)
    class FauxPDF:
        pages = [object()]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(text_extraction.pdfplumber, "open", lambda _path: FauxPDF())
    monkeypatch.setattr(
        text_extraction,
        "_extraire_texte_pdf_legacy",
        lambda _path: (_ for _ in ()).throw(AssertionError("Le repli ne doit pas être appelé")),
    )

    resultat = text_extraction._extraire_texte_detaille_sans_limite(str(chemin))

    assert resultat.moteur == "Docling (OCR intégré si nécessaire)"
    assert "mathématiques" in resultat.texte


def test_pdf_revient_a_ocr_classique_si_docling_ne_renvoie_pas_un_texte_suffisant(
    monkeypatch, tmp_path
):
    chemin = tmp_path / "scan.pdf"
    chemin.write_bytes(b"%PDF-test")

    class FauxPDF:
        pages = [object()]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(text_extraction.pdfplumber, "open", lambda _path: FauxPDF())
    monkeypatch.setattr("app.docling_extraction.docling_actif", lambda: True)
    monkeypatch.setattr("app.docling_extraction.extraire_pdf_docling", lambda *_a, **_k: "Texte très court")
    monkeypatch.setattr(
        text_extraction,
        "_extraire_texte_pdf_legacy",
        lambda _path: "Fallback OCR : contenu lisible.",
    )

    resultat = text_extraction._extraire_texte_detaille_sans_limite(str(chemin))

    assert resultat.moteur == "pdfplumber + PaddleOCR/Tesseract"
    assert "Fallback OCR" in resultat.texte


def test_docling_timeout_declenche_le_repli(monkeypatch):
    class FauxConvertisseur:
        def convert(self, chemin):
            document = SimpleNamespace(export_to_markdown=lambda: "A" * 500)
            return SimpleNamespace(
                document=document,
                status="partial_success",
                has_timeout_errors=lambda: True,
            )

    monkeypatch.setattr(docling_extraction, "docling_actif", lambda: True)
    monkeypatch.setattr(docling_extraction, "_convertisseur_docling", lambda: FauxConvertisseur())
    assert docling_extraction.extraire_pdf_docling("scan.pdf", 1000) == ""
