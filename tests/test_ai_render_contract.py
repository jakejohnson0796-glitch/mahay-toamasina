from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_renderer_ia_contient_les_garde_fous():
    # MODIF : contrat statique minimal du renderer navigateur.
    js = (ROOT / "app/static/js/rendu_ia.js").read_text(encoding="utf-8")
    assert "DOMPurify.sanitize" in js
    assert "trust: false" in js
    assert "replaceChildren" in js
    # MODIF : aucun chemin applicatif du renderer ne doit appeler innerHTML.
    assert "cible.innerHTML" not in js
    assert "element.innerHTML" not in js
    assert "renderMathInElement" in js
    assert "data-rendu" in js


def test_security_csp_autorise_les_assets_katex_sans_ouvrir_script_src():
    # MODIF : contrôle statique supplémentaire sur la politique CSP.
    code = (ROOT / "app/security_headers.py").read_text(encoding="utf-8")
    assert "https://cdn.jsdelivr.net" in code
    assert "style-src-attr 'unsafe-inline'" in code
    assert "'unsafe-inline'" not in code.split("script-src", 1)[1].split(";", 1)[0]


def test_pages_ia_exposent_le_texte_brut_au_renderer():
    # MODIF : toutes les surfaces IA attendues utilisent data-rendu.
    for path in (
        "app/templates/tuteur_reponse.html",
        "app/templates/quiz.html",
        "app/templates/quiz_passer.html",
        "app/templates/quiz_resultat.html",
        "app/templates/admin_moderation_quiz.html",
    ):
        page = (ROOT / path).read_text(encoding="utf-8")
        assert "data-rendu" in page
        assert "| texte_ia" not in page
