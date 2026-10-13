from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def lire(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_la_couche_globale_est_chargee_apres_les_styles_qui_reinitialisent_background():
    base = lire("app/templates/base.html")
    assert base.index("refonte.css") < base.index("global-design-system.css")
    assert base.index("global-design-system.css") < base.index("</head>")


def test_une_seule_fleche_personnalisee_est_imposee_aux_selects_standards():
    css = lire("app/static/global-design-system.css")
    debut = css.index("select:not([multiple]) {")
    fin = css.index("\n}", debut) + 2
    bloc = css[debut:fin]

    assert "-webkit-appearance: none !important" in bloc
    assert "appearance: none !important" in bloc
    assert "background-image: url(" in bloc
    assert "background-repeat: no-repeat !important" in bloc
    assert "background-position: right .8rem center !important" in bloc
    assert "background-size: 1rem 1rem !important" in bloc
    assert "padding-right: 2.55rem !important" in bloc


def test_fleche_de_select_a_un_contraste_adapte_dans_les_deux_themes():
    css = lire("app/static/global-design-system.css")
    debut = css.index("select:not([multiple]) {")
    fin = css.index("\n}", debut) + 2
    bloc_clair = css[debut:fin]
    debut_sombre = css.index('html[data-theme="sombre"] select:not([multiple]) {')
    fin_sombre = css.index("\n}", debut_sombre) + 2
    bloc_sombre = css[debut_sombre:fin_sombre]

    assert "stroke='%23526762'" in bloc_clair
    assert "stroke='%23B5C7C0'" in bloc_sombre
    assert "background-repeat: no-repeat !important" in bloc_clair
    # La règle commune (plus haut) fournit déjà background-repeat au thème sombre.
    assert "background-image: url(" in bloc_sombre


def test_le_correctif_ne_remplace_pas_les_listes_a_selection_multiple():
    css = lire("app/static/global-design-system.css")
    assert "select:not([multiple])" in css
    assert "select[multiple]" not in css
    assert css.count("{") == css.count("}")



def test_filtres_cercles_ne_reintroduisent_pas_la_fleche_native_ou_repetee():
    page = lire("app/templates/cercles_list.html")
    declaration_ancienne = page.index(".carte-recherche-cercles select,.carte-recherche-cercles input{")
    declaration_cible = page.index(
        ".cercles-page-shell .carte-recherche-cercles form.filtres select:not([multiple]) {"
    )
    fin_page_styles = page.index("</style>")

    assert declaration_cible > declaration_ancienne
    assert declaration_cible < fin_page_styles
    bloc_cible = page[declaration_cible:fin_page_styles]

    assert "-webkit-appearance: none !important" in bloc_cible
    assert "appearance: none !important" in bloc_cible
    assert "background-image: url(" in bloc_cible
    assert "background-repeat: no-repeat !important" in bloc_cible
    assert "background-position: right .8rem center !important" in bloc_cible
    assert "background-size: 1rem 1rem !important" in bloc_cible
    assert "html[data-theme=\\\"sombre\\\"] .cercles-page-shell .carte-recherche-cercles form.filtres select:not([multiple])" in bloc_cible
    assert "stroke='%23526762'" in bloc_cible
    assert "stroke='%23B5C7C0'" in bloc_cible
