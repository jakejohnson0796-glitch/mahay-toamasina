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
    assert "katex.render" in js
    assert "renderMathInElement" not in js
    assert "window.katex.renderMathInElement" not in js
    assert "data-rendu" in js
    assert "function convertirMarqueursTransport" in js
    assert "\\[\\[DISPLAY\\]\\]" in js
    assert "\\[\\[MATH\\]\\]" in js
    assert "[\\s\\S]*?" in js


def test_base_charge_katex_core_sans_auto_render_obligatoire():
    page = (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
    assert "katex@0.16.11/dist/katex.min.js" in page
    assert "auto-render.min.js" not in page
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
    assert "MOTIFS_LATEX_NUS" in js
    assert "trouverPremierLatexNu" in js
    assert "gm-latex-fallback" in js


def test_contrat_renderer_n_utilise_plus_auto_render_ni_delimiters_dollar():
    js = (ROOT / "app/static/js/rendu_ia.js").read_text(encoding="utf-8")
    assert "renderMathInElement" not in js
    assert '{ left: "$", right: "$"' not in js
    assert "let formule = String(item.contenu" in js
    assert "window.katex.render(formule" in js


def test_renderer_ne_depend_plus_de_auto_render():
    js = (ROOT / "app/static/js/rendu_ia.js").read_text(encoding="utf-8")
    assert "function etatDependances" in js
    assert "function restaurerMath" in js
    assert "let formule = String(item.contenu" in js
    assert "window.katex.render(formule" in js
    assert "renderMathInElement" not in js


def test_renderer_les_formules_sont_rendues_dans_le_fragment_avant_remplacement():
    js = (ROOT / "app/static/js/rendu_ia.js").read_text(encoding="utf-8")
    assert "const protection = protegerMath" in js
    assert "const resultatMarkdown = parserMarkdown" in js
    assert "const fragment = fragmentSanitise(resultatMarkdown)" in js
    assert "restaurerMath(fragment, protection.math)" in js
    assert "cible.replaceChildren(fragment)" in js


def test_mes_revisions_ne_contient_plus_l_historique_tuteur():
    page = (ROOT / "app/templates/mes_revisions.html").read_text(encoding="utf-8")
    assert "Dernières questions au Tuteur IA" not in page
    assert "hub-tuteur-grille" not in page


def test_mes_revisions_ne_reference_plus_ancienne_liste_tuteur():
    source = (ROOT / "app/routers/revisions_router.py").read_text(encoding="utf-8")
    assert '"nb_sessions_tuteur": nb_sessions_tuteur' in source
    assert 'len(sessions_tuteur)' not in source


def test_tuteur_historique_utilise_le_renderer_commun():
    page = (ROOT / "app/templates/tuteur.html").read_text(encoding="utf-8")
    assert 'class="ai-tuteur-history-question" data-rendu data-rendu-ligne' in page
    assert "data-ai-resume" not in page


def test_interactions_ia_n_ont_plus_de_renderer_texte_legacy():
    js = (ROOT / "app/static/js/ai-learning.js").read_text(encoding="utf-8")
    assert "resumeIAPlain" not in js
    assert "initialiserResumeHistoriqueTuteur" not in js


def test_renderer_protege_le_dom_katex_contre_un_second_passage():
    js = (ROOT / "app/static/js/rendu_ia.js").read_text(encoding="utf-8")
    assert '".katex, .gm-katex, .gm-latex-fallback, math, annotation, CODE, PRE"' not in js
    assert 'ancetre.classList.contains("katex")' in js
    assert 'ancetre.classList.contains("gm-katex")' in js
    assert 'ancetre.classList.contains("gm-latex-fallback")' in js
    assert 'cible.dataset.renduVersion = "5"' in js


def test_renderer_decode_les_sauts_de_ligne_ia_legacy_sans_casser_nabla():
    js = (ROOT / "app/static/js/rendu_ia.js").read_text(encoding="utf-8")
    assert "normaliserTexteMarkdownLegacy" in js
    assert r'.replace(/\\n(?=\\s*[-*•]\\s+)/g, "\n")' in js
    assert r'.replace(/\\n(?=\\s*\\d+[.)]\\s+)/g, "\n")' in js
    assert "__GASY_AI_CODE_" in js
    assert "resultat.replace(/\\x60\\x60\\x60" in js
    # La commande \\nabla reste explicitement hors des contextes de conversion.
    assert "légitime comme \\nabla." in js

def test_renderer_convertit_textit_latex_hors_math_en_italique_markdown():
    js = (ROOT / "app/static/js/rendu_ia.js").read_text(encoding="utf-8")
    assert r'.replace(/\\(?:textit|emph)\\{([^{}]*)\\}/g, "*$1*")' in js
    assert r'.replace(/\\textbf\\{([^{}]*)\\}/g, "**$1**")' in js

def test_contexte_notion_tuteur_separe_visuellement_le_libelle():
    css = (ROOT / "app/static/ai-learning.css").read_text(encoding="utf-8")
    assert ".ai-target-context .ai-kicker{display:block;" in css
