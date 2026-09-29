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
