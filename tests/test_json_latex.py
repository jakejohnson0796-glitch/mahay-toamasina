import json

from app.json_latex import charger_json_ia


def test_charge_un_json_avec_latex_correctement_echappe():
    texte = r'''{"question":"\\(x^2 + 1\\)","explication":"\\frac{1}{2}"}'''
    resultat = charger_json_ia(texte)
    assert resultat["question"] == r"\(x^2 + 1\)"
    assert resultat["explication"] == r"\frac{1}{2}"


def test_repare_un_json_ia_avec_un_antislash_latex_non_double():
    # \\sqrt n'est pas un escape JSON valide : la récupération ciblée
    # peut réintroduire le double antislash nécessaire avant json.loads.
    texte = '{"explication":"\\sqrt{x}"}'
    resultat = charger_json_ia(texte)
    assert resultat["explication"] == r"\sqrt{x}"

def test_preserve_les_delimiteurs_et_commandes_chimiques():
    texte = r'''{"math":"\\[\\begin{aligned}x&=1\\\\y&=2\\end{aligned}\\]","chimie":"\\ce{H2O}"}'''
    resultat = charger_json_ia(texte)
    assert resultat["math"] == r"\[\begin{aligned}x&=1\\y&=2\end{aligned}\]"
    assert resultat["chimie"] == r"\ce{H2O}"


def test_json_valide_preserve_saut_de_ligne():
    texte = '{"texte":"Etape 1\\nsoit x = 2"}'
    resultat = charger_json_ia(texte)
    assert resultat["texte"] == "Etape 1\nsoit x = 2"


def test_json_valide_preserve_tabulation():
    texte = '{"texte":"Total\\t10000"}'
    resultat = charger_json_ia(texte)
    assert resultat["texte"] == "Total\t10000"


def test_json_valide_preserve_retour_chariot():
    texte = '{"texte":"ligne 1\\r\\nligne 2"}'
    resultat = charger_json_ia(texte)
    assert resultat["texte"] == "ligne 1\r\nligne 2"


def test_json_valide_preserve_doubles_backslashes_latex():
    texte = r'''{"texte":"\\[
\\begin{aligned}
a &= b \\\\
c &= d
\\end{aligned}
\\]"}'''
    resultat = charger_json_ia(texte)
    assert resultat["texte"] == r"""\[
\begin{aligned}
a &= b \\
c &= d
\end{aligned}
\]"""


def test_json_invalide_recupere_uniquement_une_commande_latex_blanche():
    texte = '{"explication":"\\sqrt{x} = 1"}'
    resultat = charger_json_ia(texte)
    assert resultat["explication"] == r"\sqrt{x} = 1"

def test_json_valide_nabla_reste_un_texte_decodé_exact():
    texte = r'''{"texte":"\\nabla f"}'''
    resultat = charger_json_ia(texte)
    assert resultat["texte"] == r"\nabla f"
