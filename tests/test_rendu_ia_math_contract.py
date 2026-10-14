from pathlib import Path

from app.ia_transport import REGLES_FORMAT


RACINE = Path(__file__).resolve().parents[1]


def test_renderer_quiz_repare_les_equations_et_integrales_sans_delimiteur():
    source = (RACINE / "app" / "static" / "js" / "rendu_ia.js").read_text(encoding="utf-8")

    assert "function normaliserExpressionsMathematiquesNues(source)" in source
    assert "normaliserExpressionsMathematiquesNues(texte)" in source
    assert r"\b[fg]\s*\(\s*x\s*\)\s*=" in source
    assert r"\\int_\{" in source
    assert r'''return "\\(" + formules[Number(index)] + "\\)"''' in source


def test_renderer_preserve_code_et_formules_deja_delimitees():
    source = (RACINE / "app" / "static" / "js" / "rendu_ia.js").read_text(encoding="utf-8")

    assert "const zonesCodeProtegees" in source
    assert "const zonesMathProtegees" in source
    assert r"\\\[" in source
    assert r"\\\(" in source
    assert r"\x60\x60\x60" in source
    assert "rendreLatexNu(cible)" in source


def test_contrat_ia_exige_les_delimiteurs_maths_dans_les_qcm():
    assert "OBLIGATOIRE : chaque équation, puissance, fraction, intégrale" in REGLES_FORMAT
    assert r"« \(f(x)=3x^{2}+2x-5\) »" in REGLES_FORMAT
    assert r"« \(\displaystyle\int_{0}^{2}(x+1)\,dx\) »" in REGLES_FORMAT
    assert "Un symbole simple peut être écrit directement en Unicode" in REGLES_FORMAT
    assert r"(ex. \frac devient \\frac dans le JSON)" in REGLES_FORMAT

def test_renderer_recupere_les_fractions_des_anciens_quiz_corrompus():
    source = (RACINE / "app" / "static" / "js" / "rendu_ia.js").read_text(encoding="utf-8")

    assert r'.replace(/\u000Crac\b/g, "\\frac")' in source
    assert r'.replace(/\text(?=\s*\{)/g, "\\text")' in source
    assert r"/\(\s*(?:\\?displaystyle\s+)?(\\(?:frac|dfrac|tfrac)" in source
    assert r"/\\(?:frac|dfrac|tfrac)" in source


def test_renderer_repare_les_controles_latex_sans_toucher_au_code():
    source = (RACINE / "app" / "static" / "js" / "rendu_ia.js").read_text(encoding="utf-8")

    assert "const zonesCodeProtegees" in source
    assert "const zonesMathProtegees" in source
    assert r'.replace(/\nabla\b/g, "\\nabla")' in source
    assert r'.replace(/\rho\b/g, "\\rho")' in source
    assert "Les blocs de code et les formules bien delimitees sont deja proteges." in source


def test_contrat_anticipe_les_collisions_de_symboles_par_discipline():
    assert "le sens d'un symbole dépend de la matière et du contexte" in REGLES_FORMAT
    assert r"\\Delta et \\delta" in REGLES_FORMAT
    assert r"\\Omega et \\omega" in REGLES_FORMAT
    assert "Co n'est pas CO" in REGLES_FORMAT
    assert "unités composées et dimensions" in REGLES_FORMAT
    assert "`<=`, `!=`" in REGLES_FORMAT
    assert "Ar et MGA" in REGLES_FORMAT
    assert "Ne fais aucune substitution globale" in REGLES_FORMAT


def test_quiz_et_tuteur_gardent_un_rendu_independant_pour_chaque_bloc():
    quiz = (RACINE / "app" / "templates" / "quiz_passer.html").read_text(encoding="utf-8")
    resultat = (RACINE / "app" / "templates" / "quiz_resultat.html").read_text(encoding="utf-8")
    moderation = (RACINE / "app" / "templates" / "admin_moderation_quiz.html").read_text(encoding="utf-8")
    tuteur = (RACINE / "app" / "templates" / "tuteur_reponse.html").read_text(encoding="utf-8")

    # Les options restent quatre éléments accessibles et sélectionnables, pas un bloc A/B/C/D aplati.
    assert '{% for choix in item.choix %}' in quiz
    assert '<label class="quiz-choice">' in quiz
    assert 'value="{{ loop.index0 }}"' in quiz
    assert '<span class="quiz-choice-letter">' in quiz
    assert '<span class="quiz-choice-text" data-rendu data-rendu-ligne>{{ choix }}</span>' in quiz

    # La correction et la modération rendent aussi chaque valeur brute séparément.
    assert '<span data-rendu data-rendu-ligne>{{ choix }}</span>' in resultat
    assert '<span data-rendu data-rendu-ligne>{{ s.question.choix[s.question.index_bonne_reponse]' in moderation
    assert 'data-tuteur-content="explication" data-rendu' in tuteur
    assert 'data-tuteur-content="exemple" data-rendu' in tuteur
    assert 'data-tuteur-content="exercice" data-rendu' in tuteur
    assert 'data-tuteur-content="correction" data-rendu' in tuteur
