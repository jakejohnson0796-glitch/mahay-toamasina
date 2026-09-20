"""Garde-fous pour la refonte visuelle de la page Cercles."""

from pathlib import Path

from app.security_headers import _CSP


TEMPLATE = Path(__file__).resolve().parents[1] / "app/templates/cercles_list.html"


def test_csp_autorise_les_images_unsplash_utilisees_par_les_cercles():
    assert "img-src 'self' data: https://*.supabase.co https://images.unsplash.com;" in _CSP


def test_grille_cercles_reste_lisible_sur_desktops():
    contenu = TEMPLATE.read_text(encoding="utf-8")
    assert ".grille-cartes-claires{grid-template-columns:repeat(2,minmax(0,1fr))!important;" in contenu
    assert ".grille-cartes-claires{grid-template-columns:1fr!important}" in contenu


def test_visuels_cercles_utilisent_des_images_reelles():
    contenu = TEMPLATE.read_text(encoding="utf-8")
    assert "https://images.unsplash.com/" in contenu
    assert 'loading="lazy"' in contenu
