from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_document_auto_option_is_outside_field_grid():
    template = (ROOT / "app" / "templates" / "document_upload.html").read_text(encoding="utf-8")
    option = '<div class="document-upload-auto-option"'
    grid = '<div class="document-upload-grid">'
    assert option in template
    assert template.index(option) < template.index(grid)
    assert 'document-upload-field full">\n              <div class="document-upload-auto-box"' not in template


def test_document_drag_drop_uses_datatransfer():
    template = (ROOT / "app" / "templates" / "document_upload.html").read_text(encoding="utf-8")
    required = [
        "function definirFichiersDeposes(fileList)",
        "const transfert = new DataTransfer();",
        "transfert.items.add(file);",
        "input.files = transfert.files;",
        'input.dispatchEvent(new Event("change", { bubbles: true }));',
        "event.stopPropagation();",
        'event.dataTransfer.dropEffect = "copy";',
    ]
    for token in required:
        assert token in template, token
