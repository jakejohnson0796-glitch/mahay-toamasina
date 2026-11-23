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
