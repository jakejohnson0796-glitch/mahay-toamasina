"""Tests for academic document text extraction formats and fallbacks."""

from types import SimpleNamespace

from app import text_extraction


def test_legacy_word_extraction_uses_antiword_without_shell(monkeypatch, tmp_path):
    path = tmp_path / "cours.doc"
    path.write_bytes(b"legacy")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="Cours de droit")

    monkeypatch.setattr(text_extraction.subprocess, "run", fake_run)
    assert text_extraction.extraire_texte(str(path)) == "Cours de droit"
    assert calls[0][0][0] == "antiword"
    assert calls[0][1]["timeout"] == 25


def test_legacy_powerpoint_extraction_uses_catppt(monkeypatch, tmp_path):
    path = tmp_path / "cours.ppt"
    path.write_bytes(b"legacy")
    monkeypatch.setattr(
        text_extraction.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(
            returncode=0, stdout="Introduction\\nChapitre 1"
        ),
    )
    assert "Chapitre 1" in text_extraction.extraire_texte(str(path))


def test_webp_image_is_sent_to_ocr(monkeypatch, tmp_path):
    path = tmp_path / "annale.webp"
    path.write_bytes(b"image")
    monkeypatch.setattr(
        text_extraction, "_extraire_texte_image",
        lambda chemin: "Annale de mathématiques",
    )
    assert text_extraction.extraire_texte(str(path)) == "Annale de mathématiques"


def test_failed_legacy_converter_returns_empty_text(monkeypatch, tmp_path):
    path = tmp_path / "cours.doc"
    path.write_bytes(b"legacy")

    def fail(*args, **kwargs):
        raise FileNotFoundError("antiword absent")

    monkeypatch.setattr(text_extraction.subprocess, "run", fail)
    assert text_extraction.extraire_texte(str(path)) == ""
