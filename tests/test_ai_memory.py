from app import ai_memory


def test_categorie_et_signature_sont_deterministes():
    message = "La bonne reponse est ambiguë et plusieurs choix sont possibles."
    assert ai_memory.categorie_probleme(message) == "ambiguite"
    assert ai_memory.signature_probleme(message) == ai_memory.signature_probleme(message)


def test_enregistrer_audit_ignore_les_critiques_vides(monkeypatch):
    audit = {
        "critics": [
            {"model": "qwen/qwen3.8-27b", "avis": {"confiant": True, "problemes": []}},
        ]
    }
    assert ai_memory.enregistrer_audit_ensemble(
        audit,
        type_interaction="quiz",
        matiere="Mathematiques",
        niveau="L1",
    ) == 0


def test_contexte_recurrent_protege_les_prompts(monkeypatch):
    class FakeElement:
        categorie = "coherence"
        occurrences = 5
        modele = "qwen/qwen3.8-27b"

        derniere_detection_le = None

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def exec(self, *args):
            class Result:
                def order_by(self, *args):
                    return self

                def limit(self, *args):
                    return self

                def all(self):
                    return [FakeElement()]

            return Result()

    monkeypatch.setattr(ai_memory, "Session", lambda engine: FakeSession())

    contexte = ai_memory.contexte_erreurs_recurrentes(
        type_interaction="quiz",
        matiere="Mathematiques",
        niveau="L1",
    )

    assert "coherence" in contexte
    assert "5 occurrence(s)" in contexte
    assert "qwen/qwen3.8-27b" in contexte
