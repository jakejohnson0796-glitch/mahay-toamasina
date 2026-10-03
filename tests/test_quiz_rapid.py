from app import ai_quiz, quiz


def _questions():
    return [
        {
            "question": "2 + 2 = ?",
            "choix": ["3", "4", "5"],
            "index_bonne_reponse": 1,
            "explication": "2 + 2 vaut 4.",
            "notion": "Addition",
        }
    ]


def test_generation_rapide_ne_lance_pas_la_relecture_multi_modeles(monkeypatch):
    monkeypatch.setattr(ai_quiz, "generer_quiz_par_theme", lambda *args, **kwargs: _questions())

    def fail(*args, **kwargs):
        raise AssertionError("La relecture multi-modeles ne doit pas bloquer la generation.")

    monkeypatch.setattr(ai_quiz, "verifier_et_corriger_questions", fail)

    resultat = quiz._generer_quiz_rapide("Mathématiques", "L1", "Moyen", 1)

    assert resultat == _questions()


def test_normalise_les_formules_latex_dans_les_questions_et_reponses():
    from app.quiz_validation import normaliser_math_texte
    texte = r"\(det(A)=ad-bc\)"
    assert "det(A)=ad-bc" in normaliser_math_texte(texte)

    matrice = r"\begin{pmatrix}1&0&0\\0&3&0\\0&0&1\end{pmatrix}"
    resultat = normaliser_math_texte(matrice)
    assert "\\begin{pmatrix}" in resultat
    assert "1&0&0" in resultat
    assert "0&3&0" in resultat


def test_normalise_markdown_et_symboles_mathematiques():
    from app.quiz_validation import normaliser_math_texte
    assert normaliser_math_texte("**det(A)** = a \\times d - b \\times c") == "det(A) = a × d - b × c"


def test_rendre_math_html_echappe_le_html_du_contenu():
    from app.quiz_validation import rendre_math_html
    rendu = str(rendre_math_html(r"Question <script>alert(1)</script> et \(a+b\)"))
    assert "<script>" not in rendu
    assert "a+b" in rendu


def test_normalise_les_matrices_entre_doubles_crochets():
    from app.quiz_validation import normaliser_math_texte
    resultat = normaliser_math_texte("A = [[1,2],[3,4]]")
    assert r"\begin{pmatrix}" in resultat
    assert "1&2" in resultat
    assert "3&4" in resultat


def test_normalise_un_tableau_markdown_en_matrice():
    from app.quiz_validation import normaliser_math_texte
    texte = "| **3** | **6\\\\ 9** | **12** |\\n| :---: | :---------: | :----: |"
    resultat = normaliser_math_texte(texte)
    assert r"\\begin{pmatrix}" in resultat
    assert "3&6" in resultat
    assert "9&12" in resultat


def test_supprime_un_prefixe_de_choix_sans_casser_une_formule():
    from app.quiz_validation import normaliser_math_texte
    assert normaliser_math_texte("AIl existe B tel que AB = I") == "Il existe B tel que AB = I"
    assert normaliser_math_texte("A+B = B+A") == "A+B = B+A"


def test_reconstruit_une_matrice_3x3_aplatie_dans_un_tableau():
    from app.quiz_validation import normaliser_math_texte
    texte = (
        "| **0** | **1** | **0\\\\ 1** | **0** | "
        "**0\\\\ 0** | **0** | **1** |\\n"
        "| :---: | :---: | :---------: | :---: | :---------: | :---: | :---: |"
    )
    resultat = normaliser_math_texte(texte)
    assert r"\\begin{pmatrix}" in resultat
    assert "0&1&0" in resultat
    assert "1&0&0" in resultat
    assert "0&0&1" in resultat


def test_retirer_labels_qcm_parasites_sans_casser_ab_egal_ba():
    from app.quiz_validation import valider_questions
    questions = [{
        "question": "Quelle propriete ?",
        "choix": ["AA+B = BA", "BSi AB = O", "CLe produit existe", r"D\\lambda(AB) = A(\\lambda B)"],
        "index_bonne_reponse": 0,
        "explication": "La somme est commutative.",
        "notion": "Matrices",
    }]
    resultat = valider_questions(questions)
    assert resultat[0]["choix"][0] == "A+B = BA"
    assert resultat[0]["choix"][1] == "Si AB = O"
    assert resultat[0]["choix"][2] == "Le produit existe"
    assert "lambda" in resultat[0]["choix"][3] or "λ" in resultat[0]["choix"][3]

    formule = [{
        "question": "Identite.",
        "choix": ["AB = BA", "B = A", "C = D"],
        "index_bonne_reponse": 0,
        "explication": "Exemple.",
        "notion": "Algebre",
    }]
    resultat_formule = valider_questions(formule)
    assert resultat_formule[0]["choix"][0] == "AB = BA"


def test_normalise_les_entetes_markdown_dans_les_questions():
    from app.quiz_validation import normaliser_math_texte
    assert normaliser_math_texte("## Quelle propriete ?") == "Quelle propriete ?"


def test_rend_un_choix_ancien_avec_label_et_matrice():
    from app.quiz_validation import rendre_choix_math_html
    texte = "| **6** | **21\\\\ 24** | **3** |\\n| :---: | :-----------: | :---: |"
    rendu = str(rendre_choix_math_html("A" + texte, 0))
    assert "math-matrix" in rendu
    assert ">6<" in rendu
    assert "21" in rendu
    assert "24" in rendu
    assert ">A<" not in rendu
