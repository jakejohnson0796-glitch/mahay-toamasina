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
    attendu = r"""\[
\begin{aligned}
a &= b \\
c &= d
\end{aligned}
\]"""
    texte = json.dumps({"texte": attendu})
    resultat = charger_json_ia(texte)
    assert resultat["texte"] == attendu


def test_json_invalide_recupere_uniquement_une_commande_latex_blanche():
    texte = '{"explication":"\\sqrt{x} = 1"}'
    resultat = charger_json_ia(texte)
    assert resultat["explication"] == r"\sqrt{x} = 1"

def test_json_valide_nabla_reste_un_texte_decodé_exact():
    texte = r'''{"texte":"\\nabla f"}'''
    resultat = charger_json_ia(texte)
    assert resultat["texte"] == r"\nabla f"

def test_repare_les_commandes_latex_confondables_avec_des_escapes_json_valides():
    # La sequence \f de \frac est un escape JSON valide : json.loads seul
    # la transformerait en form-feed et laisserait "rac" au lieu de "\frac".
    texte = r'''{"question":"Simplifie (displaystyle \frac{12}{18}) ?","choix":["(\frac{2}{3})","(\frac{3}{4})","(\frac{4}{6})","(\frac{5}{9})"]}'''

    resultat = charger_json_ia(texte)

    assert resultat["question"] == r"Simplifie (displaystyle \frac{12}{18}) ?"
    assert resultat["choix"] == [
        r"(\frac{2}{3})",
        r"(\frac{3}{4})",
        r"(\frac{4}{6})",
        r"(\frac{5}{9})",
    ]


def test_repare_les_collisions_latex_text_nabla_rho_beta():
    texte = r'''{"a":"\text{valeur}","b":"\nabla f","c":"\rho","d":"\beta"}'''

    resultat = charger_json_ia(texte)

    assert resultat == {
        "a": r"\text{valeur}",
        "b": r"\nabla f",
        "c": r"\rho",
        "d": r"\beta",
    }


def test_ne_double_pas_les_antislashs_latex_deja_echappes_en_json():
    attendu = r"\frac{12}{18}"
    texte = json.dumps({"fraction": attendu})

    assert charger_json_ia(texte) == {"fraction": attendu}


def test_repare_les_commandes_grecques_majuscule_et_notations_du_guide():
    # Les commandes LaTeX du guide doivent survivre même si le modèle omet
    # l'échappement JSON des antislashs.
    texte = r'''{"variation":"\Delta x","frequence":"\Omega","ensemble":"\mathbb{R}","geometrie":"\angle ABC \perp d","logique":"A \Rightarrow B","physique":"\hbar\omega"}'''

    resultat = charger_json_ia(texte)

    assert resultat == {
        "variation": r"\Delta x",
        "frequence": r"\Omega",
        "ensemble": r"\mathbb{R}",
        "geometrie": r"\angle ABC \perp d",
        "logique": r"A \Rightarrow B",
        "physique": r"\hbar\omega",
    }


def test_preserve_exactement_les_symboles_unicode_et_contextes_du_guide():
    # Les graphies Unicode, unités, formules chimiques, opérateurs de code et
    # libellés comptables sont du contenu : le transport ne doit pas les réécrire.
    donnees = {
        "maths": "x ≤ 10; π ≈ 3,14; ℝ; ∀x, ∃y; A ∩ B; ∅",
        "physique": "v = 3 m/s; a = 2 m/s²; ρ = 1 kg/m³; Ω·m; J/(mol·K)",
        "chimie": "Co ≠ CO; H₂O(l) ⇌ 2 H⁺(aq)",
        "informatique": "a <= b && b != null; x ^ 2; obj?.value ?? 0",
        "comptabilite": "Ar 125 000; MGA; HT; TVA; TTC; P = 250",
    }

    assert charger_json_ia(json.dumps(donnees, ensure_ascii=False)) == donnees
