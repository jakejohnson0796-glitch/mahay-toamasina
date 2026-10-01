from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def lire(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_pages_a_propos_et_faq_n_utilisent_pas_de_style_inline():
    for path in ("app/templates/a_propos.html", "app/templates/aide_avis.html"):
        content = lire(path)
        assert ' style="' not in content, path


def test_base_charge_le_style_public():
    base = lire("app/templates/base.html")
    assert "public-pages.css" in base
    assert 'request.url.path in ["/a-propos", "/faq"]' in base


def test_a_propos_contient_les_sections_principales():
    page = lire("app/templates/a_propos.html")
    for terme in (
        "Pourquoi ce projet peut compter pour un étudiant",
        "Notre histoire",
        "Construire avec patience, mesurer et améliorer",
        "L'écosystème Gasy Mahay",
        "Ce que Gasy Mahay ne remplace pas",
    ):
        assert terme in page


def test_faq_contient_recherche_categories_aide_et_avis():
    page = lire("app/templates/aide_avis.html")
    for terme in (
        'id="faq-recherche"',
        'name="q"',
        'name="categorie"',
        'id="avis"',
        "Donner mon avis",
        "/mode-emploi",
        "/contact",
    ):
        assert terme in page


def test_faq_js_est_accessible_au_clavier():
    js = lire("app/static/js/faq.js")
    assert 'event.key !== "Escape"' in js
    assert 'event.key === "Enter"' in js
    assert 'event.key === " "' in js
