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
    assert "window.renderMathInElement(element" in js
    assert "window.katex.renderMathInElement" not in js
    assert "data-rendu" in js


def test_base_charge_katex_auto_render():
    # MODIF : katex.min.js ne fournit pas renderMathInElement ; l'extension
    # auto-render doit être chargée avant le renderer IA.
    page = (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
    assert "katex@0.16.11/dist/contrib/auto-render.min.js" in page
    assert "rendu_ia.js" in page


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


def test_renderer_protege_les_blocs_latex_avant_markdown():
    # MODIF : \\[ et \\( doivent survivre au parsing CommonMark de Marked.
    js = (ROOT / "app/static/js/rendu_ia.js").read_text(encoding="utf-8")
    assert "function protegerMath" in js
    assert "function restaurerMath" in js
    assert "E000GMATH_" in js
    assert "protection.source" in js
    assert "restaurerMath(fragment, protection.math)" in js


def test_quiz_en_cours_rend_aussi_le_texte_de_la_question():
    # MODIF : la question du quiz actif doit passer par le même renderer que
    # les choix, sinon son LaTeX reste brut.
    page = (ROOT / "app/templates/quiz_passer.html").read_text(encoding="utf-8")
    assert '<h2 class="quiz-question-title" data-rendu>{{ item.question }}</h2>' in page


def test_renderer_contient_un_filet_latex_nu():
    # MODIF : même si un modèle oublie les délimiteurs, le navigateur doit
    # pouvoir rendre les commandes LaTeX usuelles au lieu d'afficher du brut.
    js = (ROOT / "app/static/js/rendu_ia.js").read_text(encoding="utf-8")
    assert "COMMANDES_LATEX_NUES" in js
    assert "function rendreLatexNu" in js
    assert "window.katex.render" in js
    assert "rendreLatexNu(cible)" in js


def test_quiz_ia_utilise_un_transport_json_sans_backslash():
    # MODIF : le provider doit pouvoir parser le tool-call même lorsque le modèle
    # produit des formules mathématiques.
    code = (ROOT / "app/ai_quiz.py").read_text(encoding="utf-8")
    ensemble = (ROOT / "app/ai_ensemble.py").read_text(encoding="utf-8")
    assert "TRANSPORT JSON DU QUIZ" in code
    assert "Le caractère backslash" in code
    assert "QUIZ_MATH_INLINE_OPEN" in code
    assert "_normaliser_quiz_transport" in code
    assert "TRANSPORT JSON DU QUIZ" in ensemble


def test_quiz_transport_convertit_les_marqueurs_sans_casser_le_json():
    code = (ROOT / "app/ai_quiz.py").read_text(encoding="utf-8")
    assert "QUIZ_MATH_INLINE_OPEN = \"[[MATH]]\"" in code
    assert "QUIZ_MATH_DISPLAY_OPEN = \"[[DISPLAY]]\"" in code
    assert "def _convertir_math_transport_texte" in code
    assert "def _normaliser_quiz_transport" in code
    assert 'return r"\\[" + contenu + r"\\]"' in code
    assert 'return r"\\(" + contenu + r"\\)"' in code


def test_quiz_normalise_aussi_la_sortie_des_correcteurs():
    code = (ROOT / "app/ai_quiz.py").read_text(encoding="utf-8")
    assert "questions_finales = _normaliser_quiz_transport(questions_finales)" in code


def test_quiz_normalise_les_anciennes_tentatives_a_la_lecture():
    code = (ROOT / "app/quiz.py").read_text(encoding="utf-8")
    assert "ai_quiz._normaliser_quiz_transport" in code


def test_quiz_marker_regex_matches_real_transport_markers():
    from app.ai_quiz import _convertir_math_transport_texte

    assert _convertir_math_transport_texte("[[MATH]]det(A)=ad-bc[[/MATH]]") == r"\(\\det(A)=ad-bc\)"
    assert _convertir_math_transport_texte("[[DISPLAY]][a b ; c d][[/DISPLAY]]").startswith(r"\[\\begin{pmatrix}")
