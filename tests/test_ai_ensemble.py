from app import ai_ensemble


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


def _validate(items, expected_count):
    assert len(items) == expected_count
    return items


def test_ensemble_desactive_ne_fait_pas_dappel(monkeypatch):
    monkeypatch.setattr(ai_ensemble.parametres, "ai_ensemble_enabled", False)

    called = {"value": False}

    def fail(*args, **kwargs):
        called["value"] = True
        raise AssertionError("aucun critique ne doit etre appele")

    monkeypatch.setattr(ai_ensemble, "critiquer_quiz_groq", fail)

    questions = _questions()
    result, confiant, audit = ai_ensemble.ensemble_verification_quiz(
        questions,
        "Mathématiques",
        "L1",
        ai_ensemble.OUTIL_CRITIQUE_QUIZ,
        _validate,
    )

    assert result == questions
    assert confiant is False
    assert called["value"] is False


def test_deux_critiques_daccord_retourne_une_seule_sortie(monkeypatch):
    monkeypatch.setattr(ai_ensemble.parametres, "ai_ensemble_enabled", True)
    monkeypatch.setattr(ai_ensemble, "critiquer_quiz_groq", lambda *a, **k: {
        "questions": _questions(),
        "confiant": True,
        "problemes": [],
    })
    monkeypatch.setattr(ai_ensemble, "critiquer_quiz_gemini", lambda *a, **k: {
        "questions": _questions(),
        "confiant": True,
        "problemes": [],
    })

    def fail_arbiter(*args, **kwargs):
        raise AssertionError("pas besoin d'arbitre quand les deux critiques sont d'accord")

    monkeypatch.setattr(ai_ensemble, "arbitrer_quiz", fail_arbiter)

    result, confiant, audit = ai_ensemble.ensemble_verification_quiz(
        _questions(),
        "Mathématiques",
        "L1",
        ai_ensemble.OUTIL_CRITIQUE_QUIZ,
        _validate,
    )

    assert result == _questions()
    assert confiant is True
    assert len(audit["critics"]) == 2


def test_desaccord_des_critiques_passe_par_larbitre(monkeypatch):
    monkeypatch.setattr(ai_ensemble.parametres, "ai_ensemble_enabled", True)
    monkeypatch.setattr(ai_ensemble, "critiquer_quiz_groq", lambda *a, **k: {
        "questions": _questions(),
        "confiant": False,
        "problemes": ["Le choix correct doit etre reverifie."],
    })
    monkeypatch.setattr(ai_ensemble, "critiquer_quiz_gemini", lambda *a, **k: {
        "questions": _questions(),
        "confiant": True,
        "problemes": [],
    })

    corrected = _questions()
    corrected[0]["explication"] = "Correction arbitrée."

    monkeypatch.setattr(ai_ensemble, "arbitrer_quiz", lambda *a, **k: {
        "questions": corrected,
        "confiant": True,
    })

    result, confiant, audit = ai_ensemble.ensemble_verification_quiz(
        _questions(),
        "Mathématiques",
        "L1",
        ai_ensemble.OUTIL_CRITIQUE_QUIZ,
        _validate,
    )

    assert result[0]["explication"] == "Correction arbitrée."
    assert confiant is True
    assert audit["arbitration"] == "groq_arbiter"


def test_tuteur_reste_une_reponse_unique(monkeypatch):
    monkeypatch.setattr(ai_ensemble.parametres, "ai_ensemble_enabled", True)
    base = {
        "explication": "Explication",
        "exemple": "Exemple",
        "exercice": "Exercice",
        "correction": "Correction",
    }
    monkeypatch.setattr(ai_ensemble, "_critique_tuteur_groq", lambda *a, **k: {
        "confiant": True, "problemes": [], "ameliorations": []
    })
    monkeypatch.setattr(ai_ensemble, "_critique_tuteur_gemini", lambda *a, **k: {
        "confiant": True, "problemes": [], "ameliorations": []
    })

    result, confiant, audit = ai_ensemble.verifier_tuteur(
        base,
        "Explique les dérivées",
        "Dérivées",
        "Mathématiques",
        {},
    )

    assert result == base
    assert confiant is True
    assert len(audit["models"]) == 3
