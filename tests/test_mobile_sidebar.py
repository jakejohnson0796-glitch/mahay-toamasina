from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def lire(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_overlay_ne_recouvre_pas_la_sidebar_mobile():
    css = lire("app/static/refonte.css")
    assert ".tb-sidebar {" in css
    assert "z-index: 100;" in css
    assert ".sidebar-overlay {" in css
    assert "z-index: 90;" in css
    assert ".sidebar-bouton-mobile {" in css
    assert "z-index: 120;" in css


def test_navigation_gere_le_verrouillage_du_scroll_mobile():
    js = lire("app/static/js/navigation.js")
    assert 'document.body.classList.add("sidebar-menu-ouvert")' in js
    assert 'document.body.classList.remove("sidebar-menu-ouvert")' in js
    assert 'document.documentElement.setAttribute("data-sidebar-ouvert", "true")' in js
    assert 'document.documentElement.removeAttribute("data-sidebar-ouvert")' in js
