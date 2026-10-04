from app import ai_ensemble, ai_quiz


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


def test_tuteur_simple_ne_depense_pas_un_second_relecteur(monkeypatch):
    monkeypatch.setattr(ai_ensemble.parametres, "ai_ensemble_enabled", True)
    base = {
        "explication": "Explication simple",
        "exemple": "Exemple simple",
        "exercice": "Exercice simple",
        "correction": "Correction simple",
    }
    monkeypatch.setattr(ai_ensemble, "_critique_tuteur_groq", lambda *a, **k: {
        "confiant": True, "problemes": [], "ameliorations": []
    })

    def fail_gemini(*args, **kwargs):
        raise AssertionError("Gemini ne doit pas etre appele sur une reponse simple et confiante")

    monkeypatch.setattr(ai_ensemble, "_critique_tuteur_gemini", fail_gemini)

    result, confiant, audit = ai_ensemble.verifier_tuteur(
        base,
        "Explique les derivees",
        "Derivees",
        "Mathematiques",
        {},
    )

    assert result == base
    assert confiant is True
    assert audit["arbitration"] if "arbitration" in audit else True
    assert len(audit["models"]) == 2


def test_tuteur_complexe_demande_une_seconde_relecture(monkeypatch):
    monkeypatch.setattr(ai_ensemble.parametres, "ai_ensemble_enabled", True)
    base = {
        "explication": "Etude d'une matrice 3x3 avec determinant et systeme.",
        "exemple": r"\(\det(A) = 3\)",
        "exercice": "Calculer le determinant puis resoudre le systeme.",
        "correction": r"\(x=2\)",
    }
    called = {"gemini": False}
    monkeypatch.setattr(ai_ensemble, "_critique_tuteur_groq", lambda *a, **k: {
        "confiant": True, "problemes": [], "ameliorations": []
    })

    def gemini(*args, **kwargs):
        called["gemini"] = True
        return {"confiant": True, "problemes": [], "ameliorations": []}

    monkeypatch.setattr(ai_ensemble, "_critique_tuteur_gemini", gemini)

    result, confiant, audit = ai_ensemble.verifier_tuteur(
        base,
        "Explique ce calcul de determinant et le systeme associe ?",
        "Determinant et systemes",
        "Mathematiques",
        {},
    )

    assert result == base
    assert confiant is True
    assert called["gemini"] is True
    assert len(audit["models"]) == 3


def test_controller_refuse_retry_apres_429(monkeypatch):
    ai_ensemble.cost_controller._cooldowns.clear()
    class RateLimitError(Exception):
        status_code = 429

    err = RateLimitError("rate limit; try again in 2m")
    delay = ai_ensemble.cost_controller.record_failure("groq", err)

    assert delay >= 120
    assert not ai_ensemble.cost_controller.available("groq")

    ai_ensemble.cost_controller.clear_failure("groq")
    assert ai_ensemble.cost_controller.available("groq")



def test_resume_audit_ne_journalise_pas_le_contenu_des_problemes():
    audit = {
        "models": ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"],
        "arbitration": "groq_arbiter",
        "critics": [
            {
                "model": "qwen/qwen3.8-27b",
                "avis": {
                    "confiant": False,
                    "problemes": ["La bonne reponse est ambiguë."],
                },
            }
        ],
    }

    resume = ai_quiz._resume_audit_ensemble(audit, False)

    assert resume["total_problemes"] == 1
    assert resume["critics"][0]["problemes"] == 1
    assert resume["signatures"]
    assert "ambiguë" not in str(resume)
    assert len(resume["signatures"][0]) == 16



def test_strategie_legere_n_appelle_pas_gemini(monkeypatch):
    monkeypatch.setattr(ai_ensemble.parametres, "ai_ensemble_enabled", True)
    monkeypatch.setattr(ai_ensemble, "critiquer_quiz_groq", lambda *a, **k: {
        "questions": _questions(),
        "confiant": True,
        "problemes": [],
    })

    def fail_gemini(*args, **kwargs):
        raise AssertionError("Gemini ne doit pas etre appele en strategie legere")

    monkeypatch.setattr(ai_ensemble, "critiquer_quiz_gemini", fail_gemini)

    result, confiant, audit = ai_ensemble.ensemble_verification_quiz(
        _questions(),
        "Histoire",
        "L1",
        ai_ensemble.OUTIL_CRITIQUE_QUIZ,
        _validate,
        strategie="legere",
    )

    assert result == _questions()
    assert confiant is True
    assert audit["strategy"] == "legere"
    assert len(audit["critics"]) == 1



def test_strategie_renforcee_force_larbitrage(monkeypatch):
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
    called = {"value": False}

    def arbiter(*args, **kwargs):
        called["value"] = True
        return {"questions": _questions(), "confiant": True}

    monkeypatch.setattr(ai_ensemble, "arbitrer_quiz", arbiter)

    result, confiant, audit = ai_ensemble.ensemble_verification_quiz(
        _questions(),
        "Mathématiques",
        "L3",
        ai_ensemble.OUTIL_CRITIQUE_QUIZ,
        _validate,
        strategie="renforcee",
    )

    assert result == _questions()
    assert confiant is True
    assert audit["arbitration"] == "groq_arbiter"
    assert called["value"] is True
