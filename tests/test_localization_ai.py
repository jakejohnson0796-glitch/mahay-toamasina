from types import SimpleNamespace

from app.localization import (
    instruction_langue_sortie,
    langue_depuis_requete,
    normaliser_langue,
)
from app.ia_transport import regles_format_pour_langue


def test_locale_is_restricted_to_supported_values():
    assert normaliser_langue("en") == "en"
    assert normaliser_langue("MG") == "mg"
    assert normaliser_langue("fr") == "fr"
    assert normaliser_langue("de") == "fr"
    assert normaliser_langue(None) == "fr"


def test_server_reads_only_the_supported_locale_cookie():
    assert langue_depuis_requete(SimpleNamespace(cookies={"mahay-langue": "en"})) == "en"
    assert langue_depuis_requete(SimpleNamespace(cookies={"mahay-langue": "mg"})) == "mg"
    assert langue_depuis_requete(SimpleNamespace(cookies={"mahay-langue": "unsupported"})) == "fr"
    assert langue_depuis_requete(SimpleNamespace(cookies={})) == "fr"


def test_ai_language_contract_is_explicit_and_has_locale_correct_decimal_format():
    english = regles_format_pour_langue("en")
    malagasy = regles_format_pour_langue("mg")
    french = regles_format_pour_langue("fr")

    assert english.count("MANDATORY OUTPUT LANGUAGE: English") == 1
    assert "decimal point" in english
    assert "Fiteny tsy maintsy ampiasaina : MALAGASY" in malagasy
    assert "Use a decimal comma" in malagasy
    assert "LANGUE DE SORTIE OBLIGATOIRE : français" in french
    assert "virgule décimale française" not in english
    assert "Réponds en français" not in english
    assert "Reponds en francais" not in english
    assert r"\begin{pmatrix}" in english
    assert r"\begin{cases}" in malagasy


def test_ai_quiz_and_tutor_entrypoints_expose_a_locale_parameter():
    from inspect import signature
    from app import ai_quiz

    for name in (
        "_generer_completion_avec_reessai",
        "generer_quiz_depuis_texte",
        "generer_quiz_cible",
        "generer_quiz_par_theme",
        "verifier_et_corriger_questions",
        "verifier_comprehension_tuteur",
        "generer_reponse_tuteur",
        "verifier_reponse_tuteur_structuree",
    ):
        assert "langue" in signature(getattr(ai_quiz, name)).parameters

    from app import ai_ensemble

    assert "English" in ai_ensemble._suffixe_format_prompt(langue="en")
    assert "MALAGASY" in ai_ensemble._suffixe_format_prompt(langue="mg")



def test_personal_course_revision_prompts_use_the_stored_locale():
    from app.course_revision import _texte_ia_non_fiable, _texte_ia_reprise_compacte

    prompt_en = _texte_ia_non_fiable({"matiere": "Mathematics"}, langue="en")
    prompt_mg = _texte_ia_non_fiable({"matiere": "Mathematics"}, langue="mg")
    retry_en = _texte_ia_reprise_compacte({"matiere": "Mathematics"}, langue="en")
    retry_mg = _texte_ia_reprise_compacte({"matiere": "Mathematics"}, langue="mg")

    assert "MANDATORY OUTPUT LANGUAGE: English" in prompt_en
    assert "Fiteny tsy maintsy ampiasaina : MALAGASY" in prompt_mg
    assert "MANDATORY OUTPUT LANGUAGE: English" in retry_en
    assert "Fiteny tsy maintsy ampiasaina : MALAGASY" in retry_mg


def test_course_revision_model_persists_locale():
    from app.models import FicheRevisionCours
    from sqlalchemy import inspect

    columns = {column.key for column in inspect(FicheRevisionCours).columns}
    assert "langue" in columns



def test_revision_difficulty_labels_follow_the_selected_language():
    from app.course_revision import normaliser_fiche_revision

    contenu = {
        "resume": "Revision summary",
        "objectifs": ["Understand the method", "Apply the method"],
        "notions": [
            {"titre": f"Concept {i}", "explication": "Explanation", "exemple": "Example"}
            for i in range(3)
        ],
        "erreurs_frequentes": [
            {"erreur": f"Error {i}", "pourquoi": "Reason", "comment_eviter": "Prevention"}
            for i in range(3)
        ],
        "outils_a_retenir": [],
        "exercices": [
            {"enonce": f"Exercise {i}", "difficulte": level, "indice": "Hint",
             "correction": "Explanation", "notion": f"Concept {i}"}
            for i, level in enumerate(("Easy", "Medium", "Hard"))
        ],
        "points_a_retravailler": [],
        "plan_revision": [
            {"moment": f"Day {i}", "action": f"Action {i}"} for i in range(3)
        ],
        "auto_evaluation": [
            {"question": f"Question {i}", "reponse": f"Answer {i}"} for i in range(3)
        ],
        "limites_sources": "Based on the available course material.",
    }
    english = normaliser_fiche_revision(contenu, langue="en")
    assert [item["difficulte"] for item in english["exercices"]] == [
        "Easy", "Medium", "Hard"
    ]

    malagasy_input = {
        **contenu,
        "exercices": [
            {**item, "difficulte": level}
            for item, level in zip(contenu["exercices"], ("Mora", "Antonony", "Sarotra"))
        ],
    }
    malagasy = normaliser_fiche_revision(malagasy_input, langue="mg")
    assert [item["difficulte"] for item in malagasy["exercices"]] == [
        "Mora", "Antonony", "Sarotra"
    ]



def test_class_ai_assistants_accept_and_use_the_selected_locale(monkeypatch):
    import json
    from types import SimpleNamespace

    from app import classe_correction, classe_notes, classe_transcription
    from app.config import parametres

    monkeypatch.setattr(parametres, "groq_api_key", "test-key")
    prompts = []

    class FakeGroq:
        def __init__(self, api_key):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            prompts.append(kwargs["messages"])
            if kwargs.get("tools"):
                payload = {
                    "note_suggeree": 7,
                    "confiance": 0.8,
                    "appreciation": "The work is organised and supported.",
                    "criteres": [
                        {"nom": "Structure", "points_obtenus": 7, "commentaire": "Good structure"}
                    ],
                    "forces": ["Clear reasoning"],
                    "ameliorations": ["Add an example"],
                    "limites": "Only the extracted text was reviewed",
                }
                tool_call = SimpleNamespace(
                    function=SimpleNamespace(arguments=json.dumps(payload))
                )
                message = SimpleNamespace(tool_calls=[tool_call])
            else:
                message = SimpleNamespace(content="Generated English learning content.")
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    monkeypatch.setattr(classe_notes, "Groq", FakeGroq)
    monkeypatch.setattr(classe_correction, "Groq", FakeGroq)
    monkeypatch.setattr(classe_transcription, "Groq", FakeGroq)

    notes = classe_notes.organiser_notes(
        contenu="These are sufficiently long student notes for a language test.",
        nom_cours="Mathematics",
        titre_seance="Matrices",
        langue="en",
    )
    correction = classe_correction.generer_suggestion_correction(
        titre="Algebra",
        consigne="Solve the equation and explain your reasoning.",
        bareme=10,
        criteres=[{"nom": "Structure", "points": 10}],
        texte_copie="A sufficiently long student submission text. " * 5,
        langue="en",
    )
    summary = classe_transcription.resumer_transcription(
        contenu="A sufficiently long transcript for testing the generated summary language. " * 3,
        nom_cours="Mathematics",
        langue="en",
    )

    assert notes == "Generated English learning content."
    assert correction["appreciation"] == "The work is organised and supported."
    assert correction["forces"] == ["Clear reasoning"]
    assert summary == "Generated English learning content."
    assert len(prompts) == 3
    for messages in prompts:
        combined = "\n".join(message["content"] for message in messages)
        assert "MANDATORY OUTPUT LANGUAGE: English" in combined
        assert "Do not mix English with French or Malagasy" in combined


def test_cognitive_game_requires_english_native_questions(monkeypatch):
    from app import jeu_cerebral

    captured = {}

    monkeypatch.setattr(jeu_cerebral.ai_quiz, "_obtenir_client", lambda: object())

    def unavailable(client, messages, **kwargs):
        captured["messages"] = messages
        captured["langue"] = kwargs.get("langue")
        return None, "AI unavailable"

    monkeypatch.setattr(jeu_cerebral.ai_quiz, "_generer_completion_avec_reessai", unavailable)
    questions, source = jeu_cerebral.generer_banque_questions(
        "logique",
        "en",
        {"difficulte_depart": "Moyen"},
        utiliser_ia=True,
    )

    assert questions == []
    assert source == "langue_indisponible"
    assert captured["langue"] == "en"
    prompt = "\n".join(captured["messages"])
    assert "MANDATORY OUTPUT LANGUAGE: English" in prompt


def test_cognitive_game_does_not_use_french_local_bank_for_english(monkeypatch):
    from app import jeu_cerebral

    questions, source = jeu_cerebral.generer_banque_questions(
        "logique", "en", {}, utiliser_ia=False
    )
    assert questions == []
    assert source == "langue_indisponible"


def test_class_ai_entrypoints_expose_language_parameters():
    from inspect import signature
    from app import classe_correction, classe_notes, classe_transcription

    assert "langue" in signature(classe_notes.organiser_notes).parameters
    assert "langue" in signature(classe_correction.generer_suggestion_correction).parameters
    assert "langue" in signature(classe_transcription.resumer_transcription).parameters


def test_lesson_comparison_persists_and_uses_selected_locale():
    from sqlalchemy import inspect
    from app.models import AnalyseComparativeLecon
    from pathlib import Path

    columns = {column.key for column in inspect(AnalyseComparativeLecon).columns}
    assert "langue" in columns

    root = Path(__file__).resolve().parents[1]
    router = (root / "app" / "routers" / "harmonisation_router.py").read_text(encoding="utf-8")
    service = (root / "app" / "harmonisation_ia.py").read_text(encoding="utf-8")
    assert "langue = langue_depuis_requete(request)" in router
    assert "langue=langue" in router
    assert 'getattr(analyse, "langue", "fr")' in service
    assert "instruction_langue_sortie(langue)" in service
