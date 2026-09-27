from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_drawer_mobile_utilise_un_ordre_de_calques_correct():
    css = (ROOT / "app" / "static" / "refonte.css").read_text(encoding="utf-8")
    assert ".tb-sidebar {\n    z-index: 110 !important;" in css
    assert ".sidebar-overlay {\n    z-index: 100 !important;" in css
    assert ".sidebar-bouton-mobile {\n    z-index: 120 !important;" in css


def test_ouverture_sidebar_verrouille_le_defilement_du_fond():
    js = (ROOT / "app" / "static" / "js" / "navigation.js").read_text(encoding="utf-8")
    assert 'document.body.classList.add("menu-mobile-ouvert")' in js
    assert 'document.body.classList.remove("menu-mobile-ouvert")' in js

    css = (ROOT / "app" / "static" / "refonte.css").read_text(encoding="utf-8")
    assert "body.menu-mobile-ouvert" in css
    assert "overflow: hidden" in css
