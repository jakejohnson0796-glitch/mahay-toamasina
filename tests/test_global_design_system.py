from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def lire(path):
    return (ROOT / path).read_text(encoding="utf-8")


def contraste(hex_a: str, hex_b: str) -> float:
    def luminance(value: str) -> float:
        value = value.lstrip("#")
        rgb = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [
            channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
            for channel in rgb
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    l1, l2 = sorted((luminance(hex_a), luminance(hex_b)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def test_design_system_est_charge_apres_les_styles_de_page():
    base = lire("app/templates/base.html")
    position_design = base.rfind("global-design-system.css")
    assert position_design > base.rfind("dashboard-polish.css")
    assert position_design < base.index("</head>")
    assert "version_asset('global-design-system.css')" in base


def test_polices_disposent_des_poids_utilises_par_l_interface():
    base = lire("app/templates/base.html")
    assert "Inter:wght@400;500;600;700;800" in base
    assert "Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700" in base
    assert "IBM+Plex+Mono:wght@500;600" in base


def test_palette_claire_et_sombre_definissent_les_memes_roles():
    css = lire("app/static/global-design-system.css")
    for token in (
        "--content-bg:", "--content-surface:", "--content-border:",
        "--content-text:", "--content-text-muted:", "--content-link:",
        "--primary:", "--primary-hover:", "--primary-contrast:",
        "--accent:", "--shadow-sm:", "--radius-lg:",
        'html[data-theme="sombre"] {',
    ):
        assert token in css
    assert "prefers-reduced-motion: reduce" in css
    assert ":focus-visible" in css


def test_contraste_des_textes_et_du_bouton_primaire_respecte_wcag_aa():
    # Paires mesurées sur les fonds où les tokens sont utilisés réellement.
    assert contraste("#1B302D", "#FFFFFF") >= 7.0
    assert contraste("#526762", "#F3F7F5") >= 4.5
    assert contraste("#145F58", "#F3F7F5") >= 4.5
    assert contraste("#FFFFFF", "#176B64") >= 4.5
    assert contraste("#EDF5F1", "#172824") >= 7.0
    assert contraste("#B5C7C0", "#111F1D") >= 4.5
    assert contraste("#9BE1D7", "#111F1D") >= 4.5
    assert contraste("#102A27", "#8ED8CE") >= 4.5


def test_feuille_globale_conserve_les_etats_clavier_et_mouvement_reduit():
    css = lire("app/static/global-design-system.css")
    assert ":hover" in css
    assert ":disabled" in css
    assert ":focus-visible" in css
    assert "@media (max-width: 640px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    # Vérifie que les blocs CSS sont équilibrés, pour repérer une accolade oubliée.
    assert css.count("{") == css.count("}")
