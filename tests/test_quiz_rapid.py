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
    assert "[ " in resultat
    assert "1  0  0" in resultat
    assert "0  3  0" in resultat


def test_normalise_markdown_et_symboles_mathematiques():
    from app.quiz_validation import normaliser_math_texte
    assert normaliser_math_texte("**det(A)** = a \\times d - b \\times c") == "det(A) = a × d - b × c"
