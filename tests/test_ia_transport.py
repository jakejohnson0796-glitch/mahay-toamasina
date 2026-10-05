from app.ia_transport import (
    convertir_math_transport_texte,
    normaliser_structure_quiz,
    normaliser_structure_tuteur,
)


def test_transport_preserve_exactement_latex_inline_et_display():
    brut = r"\(\frac{a}{b}\) et \[\begin{pmatrix}1 & 2\\3 & 4\end{pmatrix}\]"
    assert convertir_math_transport_texte(brut) == brut


def test_transport_preserve_marqueurs_historiques_sans_transformation():
    brut = "Avant [[MATH]]det(A)=ad-bc[[/MATH]] puis [[DISPLAY]][1 0 ; 0 1][[/DISPLAY]] et [[CHEM]]H2O[[/CHEM]]."
    assert convertir_math_transport_texte(brut) == brut


def test_transport_preserve_latex_nu_et_doubles_antislashs():
    brut = r"Calcul : \det(A)=ad-bc; \text{unité}; \nabla f; \\frac{a}{b}"
    assert convertir_math_transport_texte(brut) == brut


def test_transport_preserve_caracteres_unicode_et_symboles():
    brut = "Élève × 10 → 20 ≤ 30 ≥ 5 ≠ 4 € — dernière ligne."
    assert convertir_math_transport_texte(brut) == brut


def test_transport_preserve_sauts_de_ligne_tabulations_et_code():
    brut = "Étape 1\nÉtape 2\t100 %\n\x60\x60\x60python\nprint(r'\\frac{a}{b}')\n\x60\x60\x60"
    assert convertir_math_transport_texte(brut) == brut


def test_normalise_structure_quiz_ne_modifie_aucun_champ_ia():
    question = {
        "question": r"Calcule \(\det(A)=ad-bc\).",
        "choix": [r"\(-2\)", "0", "2", "4"],
        "index_bonne_reponse": 0,
        "explication": r"\[\det(A)=-2\]",
        "notion": "Déterminant d'ordre 2",
    }
    resultat = normaliser_structure_quiz([question])
    assert resultat == [question]
    assert resultat[0]["choix"][0] == r"\(-2\)"


def test_normalise_structure_tuteur_ne_modifie_aucune_section():
    reponse = {
        "explication": "Évolution : \(x^2\)",
        "exemple": r"\[\begin{pmatrix}1 & 0\\2 & 1\end{pmatrix}\]",
        "exercice": r"Résous \frac{1}{2}x=3.",
        "correction": r"\(x=6\)",
    }
    resultat = normaliser_structure_tuteur(reponse)
    assert resultat == reponse


def test_transport_preserve_chimie_mhchem():
    brut = r"\(\ce{2H2 + O2 -> 2H2O}\)"
    assert convertir_math_transport_texte(brut) == brut
