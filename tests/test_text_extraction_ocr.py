from types import SimpleNamespace

from PIL import Image

from app import text_extraction


def test_pretraitement_scan_ameliore_contraste_et_taille():
    image = Image.new("RGB", (320, 180), "white")
    resultat = text_extraction._preparer_image_ocr(image)

    assert resultat.mode == "L"
    assert resultat.width >= 320
    assert resultat.height >= 180


def test_langue_ocr_utilise_francais_et_anglais_si_disponibles():
    faux_tesseract = SimpleNamespace(
        get_languages=lambda config="": ["eng", "fra", "osd"]
    )

    assert text_extraction._langue_tesseract(faux_tesseract) == "fra+eng"


def test_ocr_image_utilise_pretraitement_et_configuration_robuste(monkeypatch):
    appels = {}

    class FauxTesseract:
        @staticmethod
        def get_languages(config=""):
            return ["eng", "fra"]

        @staticmethod
        def image_to_string(image, **kwargs):
            appels.update(kwargs)
            appels["mode"] = image.mode
            return "Texte extrait"

    image = Image.new("RGB", (100, 60), "white")
    resultat = text_extraction._ocr_image(image, FauxTesseract)

    assert resultat == "Texte extrait"
    assert appels["lang"] == "fra+eng"
    assert appels["config"].startswith("--oem 1")
    assert appels["mode"] == "L"


def test_extraction_docx_lit_aussi_les_tableaux_et_en_tetes(tmp_path):
    from docx import Document as DocxDocument

    chemin = tmp_path / "support.docx"
    document = DocxDocument()
    document.add_paragraph("Cours de mathématiques")
    tableau = document.add_table(rows=1, cols=2)
    tableau.cell(0, 0).text = "Matière"
    tableau.cell(0, 1).text = "Analyse"
    document.sections[0].header.paragraphs[0].text = "Université de Toamasina"
    document.sections[0].footer.paragraphs[0].text = "Année universitaire 2026"
    document.save(chemin)

    texte = text_extraction._extraire_texte_docx(chemin)

    assert "Cours de mathématiques" in texte
    assert "Matière | Analyse" in texte
    assert "Université de Toamasina" in texte
    assert "Année universitaire 2026" in texte


def test_lecture_anciens_formats_office_utilise_un_timeout(monkeypatch, tmp_path):
    import subprocess

    appels = {}
    monkeypatch.setattr(text_extraction.shutil, "which", lambda nom: f"/usr/bin/{nom}")

    def faux_run(command, **kwargs):
        appels["command"] = command
        appels.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="Document Office")

    monkeypatch.setattr(text_extraction.subprocess, "run", faux_run)
    chemin = tmp_path / "ancien.doc"
    chemin.write_bytes(b"legacy")

    assert text_extraction._extraire_texte_bureautique_ancien(chemin, "antiword") == "Document Office"
    assert appels["timeout"] == 25
    assert appels["check"] is False


def test_pdf_mixte_ocr_uniquement_les_pages_pauvres_en_texte(monkeypatch, tmp_path):
    from contextlib import contextmanager
    from types import SimpleNamespace
    import pdf2image

    chemin = tmp_path / "mixte.pdf"
    chemin.write_bytes(b"%PDF-test")
    pages = [
        SimpleNamespace(extract_text=lambda: "Texte sélectionnable " * 12),
        SimpleNamespace(extract_text=lambda: "En-tête court"),
        SimpleNamespace(extract_text=lambda: ""),
    ]

    @contextmanager
    def faux_pdf(_chemin):
        yield SimpleNamespace(pages=pages)

    appels_ocr = []

    def faux_conversion(_chemin, **kwargs):
        appels_ocr.append((kwargs["first_page"], kwargs["last_page"]))
        return [Image.new("RGB", (100, 100), "white")]

    monkeypatch.setattr(text_extraction.pdfplumber, "open", faux_pdf)
    monkeypatch.setattr(pdf2image, "convert_from_path", faux_conversion)
    monkeypatch.setattr(
        text_extraction,
        "_ocr_image",
        lambda _image, _pytesseract: "Contenu OCR détecté",
    )

    resultat = text_extraction._extraire_texte_pdf(chemin)

    assert "Texte sélectionnable" in resultat
    assert resultat.count("Contenu OCR détecté") == 2
    assert appels_ocr == [(2, 2), (3, 3)]
