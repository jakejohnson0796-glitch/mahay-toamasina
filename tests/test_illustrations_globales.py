"""Garde-fous pour les illustrations globales du site."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app/templates/base.html"
COMPONENT = ROOT / "app/templates/components/visuel_page.html"
IMAGE_DIR = ROOT / "app/static/images/site"


def test_base_inclut_un_visuel_contextuel_global():
    contenu = BASE.read_text(encoding="utf-8")
    assert '{% include "components/visuel_page.html" %}' in contenu


def test_toutes_les_illustrations_globales_existent():
    for nom in (
        "hero-campus.svg",
        "study-books.svg",
        "documents.svg",
        "quiz.svg",
        "tuteur.svg",
        "classe.svg",
        "universite.svg",
        "community.svg",
    ):
        assert (IMAGE_DIR / nom).is_file(), nom


def test_composant_mappe_les_principales_sections():
    contenu = COMPONENT.read_text(encoding="utf-8")
    for chemin in ("/documents", "/quiz", "/tuteur", "/classe", "/universites", "/profil/academique", "/cercles"):
        assert chemin in contenu
