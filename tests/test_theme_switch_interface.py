from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def lire(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_selecteur_theme_premium_est_accessible():
    base = lire("app/templates/base.html")
    assert 'id="bouton-theme"' in base
    assert 'data-theme-label' in base
    assert 'aria-pressed="false"' in base


def test_theme_js_synchronise_etat_visuel_et_accessibilite():
    js = lire("app/static/js/theme.js")
    assert 'setAttribute("aria-pressed"' in js
    assert 'Passer au thème clair' in js
    assert 'Passer au thème sombre' in js
    assert 'localStorage.setItem(CLE_STOCKAGE, suivant)' in js


def test_theme_css_contient_les_etats_clair_sombre_et_compact():
    css = lire("app/static/refonte.css")
    for selector in (
        ".tb-toggle-theme-label",
        ".tb-toggle-theme-switch",
        ".tb-toggle-theme-switch-pastille",
        'html[data-theme="clair"] .tb-toggle-theme-switch-icon-soleil',
        'html[data-theme="sombre"] .tb-toggle-theme-switch-icon-lune',
        "body.sidebar-compact .tb-toggle-theme",
    ):
        assert selector in css
