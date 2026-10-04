import json

from app.json_latex import charger_json_ia


def test_charge_un_json_avec_latex_correctement_echappe():
    texte = r'''{"question":"\\(x^2 + 1\\)","explication":"\\frac{1}{2}"}'''
    resultat = charger_json_ia(texte)
    assert resultat["question"] == r"\(x^2 + 1\)"
    assert resultat["explication"] == r"\frac{1}{2}"


def test_repare_un_json_ia_avec_un_antislash_latex_non_double():
    # MODIF : le cas historiquement problématique \frac est réparé avant json.loads.
    texte = '{"explication":"\\frac{d}{dx}"}'
    resultat = charger_json_ia(texte)
    assert resultat["explication"] == r"\frac{d}{dx}"


def test_preserve_les_delimiteurs_et_commandes_chimiques():
    texte = r'''{"math":"\\[\\begin{aligned}x&=1\\\\y&=2\\end{aligned}\\]","chimie":"\\ce{H2O}"}'''
    resultat = charger_json_ia(texte)
    assert resultat["math"] == r"\[\begin{aligned}x&=1\\y&=2\end{aligned}\]"
    assert resultat["chimie"] == r"\ce{H2O}"
