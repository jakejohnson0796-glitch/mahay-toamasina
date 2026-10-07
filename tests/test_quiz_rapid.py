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



def test_normalise_les_matrices_entre_doubles_crochets():
    from app.quiz_validation import normaliser_math_texte
    resultat = normaliser_math_texte("A = [[1,2],[3,4]]")
    assert r"\begin{pmatrix}" in resultat
    assert "1&2" in resultat
    assert "3&4" in resultat


def test_normalise_un_tableau_markdown_en_matrice():
    from app.quiz_validation import normaliser_math_texte
    texte = """| **3** | **6\\ 9** | **12** |
| :---: | :---------: | :----: |"""
    resultat = normaliser_math_texte(texte)
    assert r"\begin{pmatrix}" in resultat
    assert "3&6" in resultat
    assert "9&12" in resultat

def test_supprime_un_prefixe_de_choix_sans_casser_une_formule():
    from app.quiz_validation import normaliser_math_texte
    assert normaliser_math_texte("AIl existe B tel que AB = I") == "Il existe B tel que AB = I"
    assert normaliser_math_texte("A+B = B+A") == "A+B = B+A"


def test_reconstruit_une_matrice_3x3_aplatie_dans_un_tableau():
    from app.quiz_validation import normaliser_math_texte
    texte = """| **0** | **1** | **0\\ 1** | **0** | **0\\ 0** | **0** | **1** |
| :---: | :---: | :---------: | :---: | :---------: | :---: | :---: |"""
    resultat = normaliser_math_texte(texte)
    assert r"\begin{pmatrix}" in resultat
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
    # MODIF : la validation peut normaliser une copie interne mais doit
    # restituer exactement le texte brut pour stockage/transmission.
    brut = questions[0]["choix"][0]
    resultat = valider_questions(questions)
    assert resultat[0]["choix"][0] == brut
    assert resultat[0]["choix"] == questions[0]["choix"]

    formule = [{
        "question": "Identite.",
        "choix": ["AB = BA", "B = A", "C = D"],
        "index_bonne_reponse": 0,
        "explication": "Exemple.",
        "notion": "Algebre",
    }]
    resultat_formule = valider_questions(formule)
    assert resultat_formule[0]["choix"] == formule[0]["choix"]


def test_normalise_les_entetes_markdown_dans_les_questions():
    from app.quiz_validation import normaliser_math_texte
    assert normaliser_math_texte("## Quelle propriete ?") == "Quelle propriete ?"


def test_normalise_labels_qcm_colles_aux_reponses_reelles():
    from app.quiz_validation import valider_questions

    questions = [{
        "question": "Quelle propriété caractérise la matrice unité I parmi les matrices carrées d'ordre n ?",
        "choix": [
            "AIA = AI = A pour toute matrice carrée A de même ordre",
            "BI est la matrice nulle",
            "CToutes les entrées de I sont égales à 0",
            "DI commute seulement avec les matrices diagonales",
        ],
        "index_bonne_reponse": 0,
        "explication": "L'identité vérifie IA = AI = A.",
        "notion": "Matrice unité",
    }]

    # MODIF : les labels collés peuvent rester dans la donnée brute ; leur
    # nettoyage n'est plus une transformation de stockage.
    brut = list(questions[0]["choix"])
    resultat = valider_questions(questions)
    assert resultat[0]["choix"] == brut


def test_normalise_labels_et_matrices_markdown_dans_les_choix():
    from app.quiz_validation import valider_questions

    questions = [{
        "question": "Soit A = | 2 | 3\\\\ 1 | 4 |. Quel est le déterminant ?",
        "choix": [
            "A-2",
            "B2",
            "C10",
            "D14",
        ],
        "index_bonne_reponse": 1,
        "explication": "det(A)=8-3=5.",
        "notion": "Déterminant",
    }]
    # MODIF : vérifie la conservation stricte du brut.
    brut = list(questions[0]["choix"])
    resultat = valider_questions(questions)
    assert resultat[0]["choix"] == brut

    choix_matrice = """A
| **1** | **2** | **3\\ 4** | **5** | **6\\ 7** | **8** | **9** |
| :---: | :---: | :---------: | :---: | :---------: | :---: | :---: |"""
    questions[0]["choix"] = [choix_matrice, "B9", "C8", "D7"]
    brut_matrice = choix_matrice
    resultat = valider_questions(questions)
    # MODIF : le texte Markdown/LaTeX reste inchangé et sera rendu côté navigateur.
    assert resultat[0]["choix"][0] == brut_matrice



def test_normalise_les_choix_qcm_des_questions_3_et_4():
    from app.quiz_validation import valider_questions

    questions = [{
        "question": "Quelle opération élémentaire ?",
        "choix": [
            "AÉchange des lignes 1 et 2",
            "BMultiplication de la ligne 1 par 0",
            "CAddition de la ligne 3 à la ligne 2",
            "DPermutation circulaire des lignes",
        ],
        "index_bonne_reponse": 0,
        "explication": "Échanger deux lignes est une opération élémentaire.",
        "notion": "Matrices",
    }, {
        "question": "Si A et B sont de type (m,n), alors la distributivité vaut si :",
        "choix": [
            "AC est une matrice de type (n,p)",
            "BC est une matrice carrée",
            "CA et B sont symétriques",
            "Dm = n",
        ],
        "index_bonne_reponse": 0,
        "explication": "Le produit AC doit être défini.",
        "notion": "Produit matriciel",
    }]

    resultat = valider_questions(questions)
    # MODIF : les choix sont conservés bruts.
    assert resultat[0]["choix"] == questions[0]["choix"]
    assert resultat[1]["choix"] == questions[1]["choix"]


def test_controle_strict_refuse_une_explication_sans_bonne_option():
    from app.quiz_validation import QuizValidationError, valider_questions

    questions = [{
        "question": "Soit A = [2 3; 1 4]. Quel est le déterminant ?",
        "choix": ["-2", "2", "10", "14"],
        "index_bonne_reponse": 1,
        "explication": (
            "det(A) = 2×4 − 3×1 = 5 ; aucune des réponses proposées ne correspond, "
            "la bonne réponse est 5."
        ),
        "notion": "Déterminant",
    }]

    try:
        valider_questions(questions, strict_coherence=True)
    except QuizValidationError:
        pass
    else:
        raise AssertionError("Une incohérence explicite ne doit pas franchir le contrôle qualité.")


def test_quality_gate_utilise_la_version_corrigee_avant_stockage(monkeypatch):
    from app import quiz

    original = _questions()[0].copy()
    corrected = _questions()[0].copy()
    corrected["choix"] = ["3", "4", "5"]
    corrected["choix"] = ["3", "4", "5"]
    corrected["index_bonne_reponse"] = 1
    corrected["explication"] = "2 + 2 vaut 4."

    monkeypatch.setattr(
        quiz.ai_quiz,
        "verifier_et_corriger_questions",
        lambda *args, **kwargs: ([corrected], True),
    )

    resultat = quiz._verifier_questions_avant_stockage(
        [original],
        "Mathématiques",
        "L1",
    )

    assert resultat == [corrected]


def test_normalise_un_quiz_avec_labels_consecutifs():
    from app.quiz_validation import valider_questions
    questions = [{
        "question": "Choisir.",
        "choix": ["AA+B = B+A", "BA+B = B-A", "CA+B = A-B", r"D\\lambda(AB) = A(\\lambda B)"],
        "index_bonne_reponse": 0,
        "explication": "Exemple.",
        "notion": "Algèbre",
    }]
    resultat = valider_questions(questions)
    # MODIF : aucune normalisation LaTeX/label n'est persistée.
    assert resultat[0]["choix"] == questions[0]["choix"]


def test_quality_gate_refuse_un_quiz_non_confirme_quand_ensemble_est_actif(monkeypatch):
    monkeypatch.setattr(quiz.parametres, "ai_ensemble_enabled", True)
    monkeypatch.setattr(
        quiz.ai_quiz,
        "verifier_et_corriger_questions",
        lambda *args, **kwargs: (_questions(), False),
    )
    from app.quiz_validation import QuizValidationError
    try:
        quiz._verifier_questions_avant_stockage(
            _questions(),
            "Mathématiques",
            "L1",
        )
    except QuizValidationError:
        pass
    else:
        raise AssertionError("Un quiz non confirmé ne doit pas être publié avec l'ensemble actif.")


def test_creer_tentative_ne_bloque_plus_sur_la_relecture_multi_modeles():
    import json
    from unittest.mock import Mock
    from app import quiz

    utilisateur = Mock(id=23)
    session = Mock()
    session.add = Mock()
    session.commit = Mock()
    session.refresh = Mock()

    original = quiz._generer_quiz_rapide
    original_validator = quiz.valider_questions
    try:
        questions_cinq = _questions() * 5
        quiz._generer_quiz_rapide = lambda *args, **kwargs: questions_cinq
        quiz.valider_questions = lambda questions, **kwargs: questions

        resultat = quiz.creer_tentative(
            session,
            utilisateur,
            "Mathématiques",
            "L1",
            "Moyen",
            5,
        )
        assert resultat.nb_questions == 5
        assert json.loads(resultat.questions_json)[0]["question"] == "2 + 2 = ?"
    finally:
        quiz._generer_quiz_rapide = original
        quiz.valider_questions = original_validator


def test_quiz_cible_n_utilise_pas_un_budget_inexistant(monkeypatch):
    from app import ai_quiz

    monkeypatch.setattr(ai_quiz, "_obtenir_client", lambda: object())
    monkeypatch.setattr(
        ai_quiz.ai_memory,
        "contexte_erreurs_recurrentes",
        lambda **kwargs: "",
    )
    captured = {}

    class _Message:
        tool_calls = []

    class _Choice:
        message = _Message()

    class _Completion:
        choices = [_Choice()]

    def fake_completion(client, messages, max_completion_tokens, expected_count):
        captured["max_completion_tokens"] = max_completion_tokens
        captured["expected_count"] = expected_count
        return _Completion(), None

    monkeypatch.setattr(ai_quiz, "_generer_completion_avec_reessai", fake_completion)
    monkeypatch.setattr(
        ai_quiz,
        "_extraire_questions",
        lambda completion, expected_count=5: _questions()[:expected_count],
    )

    result = ai_quiz.generer_quiz_cible(
        "Mathématiques",
        "L1",
        "Déterminant d'ordre 2",
        5,
    )

    assert result == _questions()[:5]
    assert captured == {"max_completion_tokens": 2048, "expected_count": 5}
