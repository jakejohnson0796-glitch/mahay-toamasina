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
        "Pourquoi Gasy Mahay existe",
        "Une histoire construite autour d'un besoin concret",
        "Notre approche de l'intelligence artificielle",
        "Notre manière de construire",
        "Ce que la plateforme ne remplace pas",
    ):
        assert terme in page
    assert "14 J" in page
    assert "60 J" in page
    assert 'class="public-timeline"' in page
    assert "public-card-emphasis" in page



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
    assert 'class="faq-help-paths"' in page
    assert "faq-ai-trial-card" in page
    assert "Pour un retour utile" in page



def test_faq_js_est_accessible_au_clavier():
    js = lire("app/static/js/faq.js")
    assert 'event.key !== "Escape"' in js
    assert 'event.key === "Enter"' in js
    assert 'event.key === " "' in js
