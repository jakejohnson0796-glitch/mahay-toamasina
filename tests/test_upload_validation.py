import io
import zipfile

from PIL import Image

from app.upload_validation import valider_upload


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(buf, format="PNG")
    return buf.getvalue()


def _docx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<document/>")
    return buf.getvalue()


def test_rejects_extension_spoofed_pdf():
    try:
        valider_upload(b"<html>not a pdf</html>", "cours.pdf", 1024, {".pdf"})
    except ValueError as exc:
        assert "PDF" in str(exc)
    else:
        raise AssertionError("Un faux PDF doit etre rejete.")


def test_rejects_wrong_real_image_format():
    try:
        valider_upload(_png_bytes(), "photo.jpg", 1024 * 1024, {".jpg"})
    except ValueError as exc:
        assert "extension" in str(exc).lower() or "jpeg" in str(exc).lower()
    else:
        raise AssertionError("Une image PNG renommee en JPG doit etre rejetee.")


def test_accepts_real_docx():
    mime = valider_upload(_docx_bytes(), "support.docx", 1024 * 1024, {".docx"})
    assert mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_rejects_zip_path_traversal():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("../evil.txt", "x")
        z.writestr("word/document.xml", "<document/>")
    try:
        valider_upload(buf.getvalue(), "support.docx", 1024 * 1024, {".docx"})
    except ValueError as exc:
        assert "chemin" in str(exc).lower()
    else:
        raise AssertionError("Un OOXML avec chemin traverse doit etre rejete.")
