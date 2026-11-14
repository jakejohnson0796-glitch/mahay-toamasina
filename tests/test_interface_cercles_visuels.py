"""Garde-fous pour la refonte visuelle de la page Cercles."""

from pathlib import Path

from app import security_headers


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app/templates/cercles_list.html"
IMAGE_DIR = ROOT / "app/static/images/cercles"


def test_csp_autorise_les_images_locales(monkeypatch):
    monkeypatch.setattr(security_headers.parametres, "supabase_url", "")
    csp = security_headers._construire_csp("test-nonce")
    directive_images = next(
        directive.strip()
        for directive in csp.split(";")
        if directive.strip().startswith("img-src ")
    )
    assert directive_images == "img-src 'self' data:"


def test_csp_autorise_uniquement_l_origine_supabase_configuree(monkeypatch):
    monkeypatch.setattr(
        security_headers.parametres,
        "supabase_url",
        "https://projet-demo.supabase.co/storage/v1",
    )
    csp = security_headers._construire_csp("test-nonce")
    directive_images = next(
        directive.strip()
        for directive in csp.split(";")
        if directive.strip().startswith("img-src ")
    )
    assert directive_images == "img-src 'self' data: https://projet-demo.supabase.co"
    assert "*.supabase.co" not in directive_images


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
