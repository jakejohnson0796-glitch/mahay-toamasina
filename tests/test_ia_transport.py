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


def test_tuteur_corrige_les_divisions_euclidiennes_dans_les_reponses_historiques():
    tick = chr(96)
    explication = (
        "En appliquant l'algorithme d'Euclide :\n"
        " - " + tick + "123456=156" + tick + "\t" + "imes789 + 462\n"
        " - " + tick + "789=1" + tick + r"\times462 + 327" + "\n"
        " - " + tick + "462=1" + tick + r"\times327 + 135" + "\n"
        " - " + tick + "327=2" + tick + r"\times135 + 57" + "\n"
        " - " + tick + "135=2" + tick + r"\times57 + 21" + "\n"
        " - " + tick + "57=2" + tick + r"\times21 + 15" + "\n"
        " - " + tick + "21=1" + tick + r"\times15 + 6" + "\n"
        " - " + tick + "15=2" + tick + r"\times6 + 3" + "\n"
        " - " + tick + "6=2" + tick + r"\times3 + 0"
    )
    resultat = normaliser_structure_tuteur({"explication": explication})["explication"]

    assert r"\(123456=156\times789+372\)" in resultat
    assert r"\(789=2\times372+45\)" in resultat
    assert r"\(372=8\times45+12\)" in resultat
    assert r"\(45=3\times12+9\)" in resultat
    assert r"\(12=1\times9+3\)" in resultat
    assert r"\(9=3\times3+0\)" in resultat
    assert r"\(789=1\times462+327\)" not in resultat
    assert r"\(462=1\times327+135\)" not in resultat
    assert tick + "123456=156" + tick not in resultat
    assert "123456=156" + "\t" + "imes789 + 462" not in resultat


    assert "123456=156" + "\t" + "imes789 + 462" not in resultat


def test_quiz_corrige_aussi_les_restes_euclidiens_mal_formates():
    tick = chr(96)
    questions = [{
        "question": "Calcule le PGCD de 123456 et 789 avec l'algorithme d'Euclide.",
        "choix": ["3", "6", "9", "12"],
        "index_bonne_reponse": 0,
        "explication": (
            "Euclide : " + tick + "123456=156" + tick + r"\times789 + 462"
        ),
    }]

    resultat = normaliser_structure_quiz(questions)

    assert r"\(123456=156\times789+372\)" in resultat[0]["explication"]
    assert " + 462" not in resultat[0]["explication"]


def test_tuteur_nettoie_les_expansions_euclide_coupees_par_backticks():
    tick = chr(96)
    explication = (
        "Algorithme d'Euclide :\n"
        " - " + tick + "987654321=8000" + tick
        + r"\times123456 + 987654321 - 8000\times123456 = "
        + tick + "987654321−987648000=6321" + tick + "\n"
        " - " + tick + "123456=19" + tick
        + r"\times6321 + 123456 - 19\times6321 = "
        + tick + "123456−120099=3357" + tick
    )

    resultat = normaliser_structure_tuteur({"explication": explication})["explication"]

    assert r"\(987654321=8000\times123456+6321\)" in resultat
    assert r"\(123456=19\times6321+3357\)" in resultat
    assert "987654321−987648000" not in resultat
    assert "123456−120099" not in resultat
    assert r"\(2964=7\times393+213\)" in resultat
    assert r"\(393=1\times213+180\)" in resultat
    assert r"\(213=1\times180+33\)" in resultat
    assert r"\(33=2\times15+3\)" in resultat
    assert r"\(15=5\times3+0\)" in resultat
    assert "393=1\\times315+78" not in resultat
    assert tick not in resultat


def test_transport_preserve_chimie_mhchem():
    brut = r"\(\ce{2H2 + O2 -> 2H2O}\)"
    assert convertir_math_transport_texte(brut) == brut
