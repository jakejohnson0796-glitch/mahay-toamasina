from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _template_document_upload():
    return (ROOT / "app" / "templates" / "document_upload.html").read_text(encoding="utf-8")


def test_glisser_deposer_remplit_input_et_declenche_le_flux_normal():
    template = _template_document_upload()
    required = [
        "function definirFichiersDeposes(fileList)",
        "const transfert = new DataTransfer();",
        "transfert.items.add(file);",
        "input.files = transfert.files;",
        "input.files = fileList;",
        'input.dispatchEvent(new Event("change", { bubbles: true }));',
        'input.addEventListener("change", function () { maj(); detecterFichier(); });',
        'zone.addEventListener("drop", function (event)',
        "event.stopPropagation();",
    ]
    for token in required:
        assert token in template, token


def test_depot_de_fichier_hors_zone_navigue_pas_vers_le_fichier():
    template = _template_document_upload()
    required = [
        'document.addEventListener("dragover", function (event)',
        'document.addEventListener("drop", function (event)',
        'types.includes("Files")',
        'event.dataTransfer.dropEffect = "copy";',
        '(!zone || !zone.contains(event.target))',
    ]
    for token in required:
        assert token in template, token
