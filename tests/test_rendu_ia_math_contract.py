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

    assert "const zonesProtegees" in source
    assert r"\\\[" in source
    assert r"\\\(" in source
    assert r"\x60\x60\x60" in source
    assert "rendreLatexNu(cible)" in source


def test_contrat_ia_exige_les_delimiteurs_maths_dans_les_qcm():
    assert "OBLIGATOIRE : chaque équation, puissance, fraction, intégrale" in REGLES_FORMAT
    assert r"« \(f(x)=3x^{2}+2x-5\) »" in REGLES_FORMAT
    assert r"« \(\displaystyle\int_{0}^{2}(x+1)\,dx\) »" in REGLES_FORMAT

def test_renderer_recupere_les_fractions_des_anciens_quiz_corrompus():
    source = (RACINE / "app" / "static" / "js" / "rendu_ia.js").read_text(encoding="utf-8")

    assert r".replace(/\u000C(?=rac\b)/g, \"\\frac\")" in source
    assert r".replace(/\t(?=ext\b)/g, \"\\text\")" in source
    assert r"/\(\s*(?:\\?displaystyle\s+)?(\\(?:frac|dfrac|tfrac)" in source
    assert r"/\\(?:frac|dfrac|tfrac)" in source


def test_renderer_repare_les_controles_latex_sans_toucher_au_code():
    source = (RACINE / "app" / "static" / "js" / "rendu_ia.js").read_text(encoding="utf-8")

    assert "const zonesProtegees" in source
    assert r".replace(/\n(?=abla\b)/g, \"\\nabla\")" in source
    assert r".replace(/\r(?=ho\b)/g, \"\\rho\")" in source
    assert "Les blocs de code et les formules bien delimitees sont deja proteges." in source

