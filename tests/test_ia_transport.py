from app.ia_transport import (
    convertir_math_transport_texte,
    normaliser_structure_quiz,
    normaliser_structure_tuteur,
)


def test_convertit_marquage_inline_en_latex():
    valeur = convertir_math_transport_texte("[[MATH]]det(A)=ad-bc[[/MATH]]")
    assert valeur.startswith(r"\(")
    assert r"\det(A)=ad-bc" in valeur
    assert valeur.endswith(r"\)")


def test_convertit_marquage_display_en_matrice_katex():
    valeur = convertir_math_transport_texte("[[DISPLAY]][2 3 ; 1 4][[/DISPLAY]]")
    assert valeur.startswith(r"\[")
    assert r"\begin{pmatrix}" in valeur
    assert "2 & 3" in valeur
    assert r"\end{pmatrix}" in valeur


def test_normalise_structure_quiz_sur_tous_les_champs_ia():
    questions = normaliser_structure_quiz([
        {
            "question": "Calcule [[MATH]]det(A)=ad-bc[[/MATH]].",
            "choix": [
                "[[MATH]]-2[[/MATH]]",
                "0",
                "2",
                "4",
            ],
            "index_bonne_reponse": 0,
            "explication": "[[MATH]]det(A)=-2[[/MATH]]",
            "notion": "Déterminant",
        }
    ])
    assert "[[MATH]]" not in questions[0]["question"]
    assert "[[MATH]]" not in questions[0]["choix"][0]
    assert "[[MATH]]" not in questions[0]["explication"]


def test_normalise_structure_tuteur_sur_les_quatre_sections():
    reponse = normaliser_structure_tuteur({
        "explication": "[[MATH]]x^2[[/MATH]]",
        "exemple": "[[DISPLAY]][1 0 ; 0 1][[/DISPLAY]]",
        "exercice": "Résous [[MATH]]2x=4[[/MATH]].",
        "correction": "[[MATH]]x=2[[/MATH]]",
    })
    assert all("[[MATH]]" not in valeur and "[[DISPLAY]]" not in valeur for valeur in reponse.values())
    assert all(valeur for valeur in reponse.values())


def test_convertit_chimie_en_mhchem():
    valeur = convertir_math_transport_texte("[[CHEM]]2H2 + O2 -> 2H2O[[/CHEM]]")
    assert r"\ce{2H2 + O2" in valeur
    assert "[[CHEM]]" not in valeur


def test_preserve_les_sauts_de_ligne_et_nabla():
    brut = r"Explication.\nLors du calcul : \nAmortissement annuel. \nabla f"
    assert convertir_math_transport_texte(brut) == brut


def test_structure_tuteur_preserve_les_sauts_decodes():
    reponse = normaliser_structure_tuteur({
        "explication": "Étape 1\nÉtape 2\nLa formule : \(x^2\)",
        "exemple": "",
        "exercice": "",
        "correction": "",
    })
    assert reponse["explication"] == "Étape 1\nÉtape 2\nLa formule : \(x^2\)"


def test_normalise_le_latex_nu_exact_du_tuteur():
    brut = (
        "Calculs\n"
        "\\det = a*d - b*c; = (-4)*(-2) - 6*1; = 8 - 6; = 2"
    )
    valeur = convertir_math_transport_texte(brut)
    assert "\\(" in valeur
    assert "\\det = a*d - b*c; = (-4)*(-2) - 6*1; = 8 - 6; = 2\\)" in valeur

def test_normalise_un_begin_matrix_nu_en_bloc():
    brut = "\\begin{bmatrix} -4 & 6 \\\\ 1 & -2 \\end{bmatrix}"
    valeur = convertir_math_transport_texte(brut)
    assert "\\[" in valeur
    assert "\\begin{bmatrix}" in valeur
    assert "\\]" in valeur

def test_ne_wrappe_pas_le_code_avec_une_commande_latex():
    brut = "```text\n\\det = a*d - b*c\n```"
    valeur = convertir_math_transport_texte(brut)
    assert valeur == brut

def test_separe_correctement_une_formule_nue_dune_phrase_suivante():
    brut = "\\det(A)=ad-bc. Ensuite, on verifie le resultat."
    valeur = convertir_math_transport_texte(brut)
    assert "\\(\\det(A)=ad-bc\\)." in valeur
    assert "Ensuite, on verifie le resultat." in valeur


def test_normalise_une_formule_nue_de_quiz_avec_lambda():
    valeur = convertir_math_transport_texte(
        r"\lambda A + \beta B = \gamma C + \delta D"
    )
    assert valeur.startswith(r"\(")
    assert r"\lambda A + \beta B" in valeur
    assert valeur.endswith(r"\)")


def test_preserve_un_bloc_latex_multiligne_intact():
    brut = r"""\[
\begin{aligned}
a &= b \\
c &= d
\end{aligned}
\]"""
    assert convertir_math_transport_texte(brut) == brut


def test_preserve_un_bloc_matrice_multiligne_intact():
    brut = r"""\[
\begin{pmatrix}
1 & 2 \\
3 & 4
\end{pmatrix}
\]"""
    assert convertir_math_transport_texte(brut) == brut


def test_ne_modifie_pas_le_code_multiligne():
    brut = "\x60\x60\x60python\nprint(\"Total:\\nAriary\")\nprint(r\"\\frac{a}{b}\")\n\x60\x60\x60"
    assert convertir_math_transport_texte(brut) == brut


def test_ne_modifie_pas_le_code_inline():
    brut = "\x60\\(\\d+\\)\x60 et du texte"
    assert convertir_math_transport_texte(brut) == brut


def test_preserve_les_formules_physique_et_chimie_delimitees():
    valeurs = [
        r"\( \mathrm{m\,s^{-2}} \)",
        r"\( \vec{F} \)",
        r"\( \nabla \times \vec{E} \)",
        r"\( \ce{H2O} \)",
        r"\( \ce{2H2 + O2 -> 2H2O} \)",
        r"\( \ce{Fe^{3+}} \)",
    ]
    for valeur in valeurs:
        assert convertir_math_transport_texte(valeur) == valeur


def test_ne_convertit_plus_les_sauts_litteraux_arbitrairement():
    brut = r"Etape 1\nsoit x = 2"
    assert convertir_math_transport_texte(brut) == brut
