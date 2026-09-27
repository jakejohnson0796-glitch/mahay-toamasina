from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_classe_charge_un_theme_dedie():
    base = read("app/templates/base.html")
    assert 'version_asset(\'classe.css\')' in base
    assert 'request.url.path.startswith("/classe")' in base


def test_sidebar_charge_un_theme_dedie_et_un_controle_compact():
    base = read("app/templates/base.html")
    nav = read("app/static/js/navigation.js")
    css = read("app/static/sidebar.css")
    assert 'version_asset(\'sidebar.css\')' in base
    assert 'bouton-sidebar-collapse' in base
    assert 'mahay-sidebar-compact' in nav
    assert '.tb-sidebar-collapse' in css
    assert 'sidebar-compact' in css


def test_interfaces_classe_principales_n_ont_pas_de_style_inline():
    paths = [
        "app/templates/classe_liste.html",
        "app/templates/classe_detail.html",
        "app/templates/classe_salle.html",
        "app/templates/classe_devoir.html",
        "app/templates/classe_etudiants.html",
        "app/templates/classe_presences.html",
        "app/templates/classe_tableau.html",
    ]
    for path in paths:
        content = read(path)
        assert ' style="' not in content, path


def test_salle_conserve_le_chat_et_les_controles_live():
    salle = read("app/templates/classe_salle.html")
    for identifiant in (
        'id="grille-video"',
        'id="btn-micro"',
        'id="btn-camera"',
        'id="btn-tableau"',
        'id="btn-participants"',
        'id="form-chat-salle"',
        'id="champ-chat-salle"',
        'id="form-quitter"',
    ):
        assert identifiant in salle


def test_css_classe_couvre_responsive_et_salle():
    css = read("app/static/classe.css")
    for selector in (
        ".classe-hero",
        ".classe-grid",
        ".classe-salle-stage",
        ".classe-salle-controls",
        ".classe-chat",
        "@media (max-width: 820px)",
        "@media (max-width: 520px)",
    ):
        assert selector in css
