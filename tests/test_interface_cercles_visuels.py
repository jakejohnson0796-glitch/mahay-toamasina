"""Garde-fous pour la refonte visuelle de la page Cercles."""

from pathlib import Path

from app.security_headers import _CSP


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app/templates/cercles_list.html"
IMAGE_DIR = ROOT / "app/static/images/cercles"


def test_csp_autorise_les_images_locales():
    assert "img-src 'self' data: https://*.supabase.co;" in _CSP


def test_grille_cercles_reste_lisible_sur_desktops():
    contenu = TEMPLATE.read_text(encoding="utf-8")
    assert ".grille-cartes-claires{grid-template-columns:repeat(2,minmax(0,1fr))!important;" in contenu
    assert ".grille-cartes-claires{grid-template-columns:1fr!important}" in contenu


def test_visuels_cercles_sont_locaux_et_existants():
    contenu = TEMPLATE.read_text(encoding="utf-8")
    assert "https://images.unsplash.com/" not in contenu
    assert "/static/images/cercles/livre-1.svg" in contenu
    assert "/static/images/cercles/livre-2.svg" in contenu
    assert "/static/images/cercles/livre-3.svg" in contenu
    assert "/static/images/cercles/livre-4.svg" in contenu
    for numero in range(1, 5):
        assert (IMAGE_DIR / f"livre-{numero}.svg").is_file()
