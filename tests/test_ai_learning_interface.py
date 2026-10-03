from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def lire(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_base_charge_les_assets_quiz_tuteur():
    base = lire("app/templates/base.html")
    assert 'version_asset(\'ai-learning.css\')' in base
    assert 'version_asset(\'ai-learning.js\')' in base
    assert 'request.url.path.startswith("/quiz")' in base
    assert 'request.url.path.startswith("/tuteur")' in base


def test_pages_quiz_et_tuteur_n_ajoutent_pas_de_style_ou_script_inline():
    paths = [
        "app/templates/quiz_config.html",
        "app/templates/quiz_passer.html",
        "app/templates/quiz_resultat.html",
        "app/templates/quiz_historique.html",
        "app/templates/quiz_reflexion.html",
        "app/templates/quiz.html",
        "app/templates/tuteur.html",
        "app/templates/tuteur_reponse.html",
    ]
    for path in paths:
        template = lire(path)
        assert ' style="' not in template, path
        assert "<script" not in template, path


def test_interface_quiz_contient_navigation_et_progression():
    quiz = lire("app/templates/quiz_passer.html")
    assert "data-quiz-form" in quiz
    assert "data-quiz-nav" in quiz
    assert "data-quiz-progress-fill" in quiz
    assert "data-quiz-submit" in quiz


def test_interface_tuteur_contient_suggestions_et_compteur():
    tuteur = lire("app/templates/tuteur.html")
    assert "data-tuteur-question" in tuteur
    assert "data-tuteur-count" in tuteur
    assert "data-tuteur-prompt" in tuteur
    assert "data-tuteur-form" in tuteur


def test_css_et_js_dedies_exist():
    assert (ROOT / "app/static/ai-learning.css").exists()
    assert (ROOT / "app/static/js/ai-learning.js").exists()


def test_filtre_texte_ia_rend_les_formules_mathematiques():
    from app.templating import templates

    filtre = templates.env.filters["texte_ia"]
    rendu = str(filtre(r"Explique : \\(x^2 + 1\\) puis la matrice \\[\\begin{pmatrix}1&2\\\\3&4\\end{pmatrix}\\]."))
    assert "x^2 + 1" in rendu
    assert "math-matrix" in rendu
    assert "<table" in rendu
    assert r"\\begin{pmatrix}" not in rendu
    assert r"\\[" not in rendu


def test_page_tuteur_indique_une_verification_avant_enregistrement():
    tuteur = lire("app/templates/tuteur.html")
    assert "vérifiée par plusieurs modèles avant d'être enregistrée" in tuteur


def test_filtre_texte_ia_gere_aussi_le_latex_doublement_echappe():
    from app.templating import templates

    filtre = templates.env.filters["texte_ia"]
    rendu = str(filtre(r"Formule : \\[x^2 + 1\\] et \\begin{pmatrix}1&2\\\\3&4\\end{pmatrix}."))
    assert "x^2 + 1" in rendu
    assert "math-matrix" in rendu
    assert r"\\[" not in rendu
    assert r"\\begin{pmatrix}" not in rendu


def test_route_tuteur_persiste_le_statut_de_verification():
    route = lire("app/routers/tuteur_router.py")
    assert 'statut_verification = reponse.pop("_statut_verification", "terminee")' in route
    assert 'statut_verification_ia=statut_verification' in route


def test_filtre_texte_ia_rend_une_matrice_embarquee_dans_une_formule():
    from app.templating import templates

    filtre = templates.env.filters["texte_ia"]
    rendu = str(
        filtre(
            r"Pour une matrice \\[A=\\begin{pmatrix}a & b\\\\ c & d\\end{pmatrix}\\], "
            r"les vecteurs sont \\(\\mathbf{u}=(a,c)\\) et \\(\\mathbf{v}=(b,d)\\)."
        )
    )
    assert "math-matrix" in rendu
    assert "<td>a</td>" in rendu
    assert "<td>d</td>" in rendu
    assert "<strong>u</strong>" in rendu
    assert "A=" in rendu
    assert "begin{pmatrix}" not in rendu
    assert "end{pmatrix}" not in rendu
    assert "\\times" not in rendu


def test_filtre_texte_ia_convertit_un_tableau_markdown_en_matrice():
    from app.templating import templates

    filtre = templates.env.filters["texte_ia"]
    rendu = str(
        filtre(
            r"""Pour une matrice
| a | b |
| - | - |
| c | d |

et det(B)=1\\times4 - 2\\times3 = -2."""
        )
    )
    assert "math-matrix" in rendu
    assert "<td>a</td>" in rendu
    assert "<td>b</td>" in rendu
    assert "<td>c</td>" in rendu
    assert "<td>d</td>" in rendu
    assert "ai-markdown-table" not in rendu
    assert "1×4" in rendu


def test_filtre_texte_ia_reconstruit_une_matrice_brute_sur_plusieurs_lignes():
    from app.templating import templates

    filtre = templates.env.filters["texte_ia"]
    rendu = str(
        filtre(
            "Pour une matrice\\n"
            "A=\\n"
            "a b\\n"
            "c d\\n"
            ",\\n"
            "les colonnes sont les vecteurs u=(a,c) et v=(b,d)."
        )
    )
    assert "math-matrix" in rendu
    assert "<td>a</td>" in rendu
    assert "<td>b</td>" in rendu
    assert "<td>c</td>" in rendu
    assert "<td>d</td>" in rendu
    assert "A=" in rendu
    assert "<p>,</p>" not in rendu
    assert "begin{pmatrix}" not in rendu


def test_filtre_texte_ia_nettoie_les_commandes_latex_sans_delimiters():
    from app.templating import templates

    filtre = templates.env.filters["texte_ia"]
    rendu = str(filtre(r"Les vecteurs sont \\mathbf{u}=(a,c) et \\mathbf{v}=(b,d)."))
    assert "mathbf" not in rendu
    assert "<strong>u</strong>=(a,c)" in rendu
