"""Regression tests for locale-complete document summaries."""

from app import document_summary


def _payload_trilingue():
    return {
        "resume": "Résumé français vérifié.",
        "objectif_pedagogique": "Comprendre le sujet.",
        "type_cours": "Support de cours",
        "niveau_cible": "Niveau non déterminé",
        "notions_cles": ["Notion française"],
        "competences_visees": ["Compétence française"],
        "prerequis": ["Prérequis français"],
        "plan_cours": ["Étape française"],
        "langue": "Français",
        "confiance": 0.9,
        "limites": "Limites françaises.",
        "resume_mg": "Famintinana amin'ny teny malagasy.",
        "objectif_pedagogique_mg": "Mahafantatra ny lohahevitra.",
        "type_cours_mg": "Lesona",
        "niveau_cible_mg": "Ambaratonga tsy voafaritra",
        "notions_cles_mg": ["Hevi-dehibe"],
        "competences_visees_mg": ["Fahaiza-manao"],
        "prerequis_mg": ["Fahalalana ilaina"],
        "plan_cours_mg": ["Dingana voalohany"],
        "langue_mg": "Malagasy",
        "limites_mg": "Fetra.",
        "resume_en": "Verified English summary.",
        "objectif_pedagogique_en": "Understand the subject.",
        "type_cours_en": "Course material",
        "niveau_cible_en": "Target level not determined",
        "notions_cles_en": ["Key topic"],
        "competences_visees_en": ["Skill"],
        "prerequis_en": ["Prerequisite"],
        "plan_cours_en": ["First step"],
        "langue_en": "French",
        "limites_en": "Limitations.",
    }


def test_document_summary_contract_requires_french_malagasy_and_english():
    required = set(
        document_summary.OUTIL_FICHE_PEDAGOGIQUE["function"]["parameters"]["required"]
    )
    assert {"resume", "resume_mg", "resume_en"} <= required
    assert {
        "objectif_pedagogique_en",
        "type_cours_en",
        "niveau_cible_en",
        "notions_cles_en",
        "competences_visees_en",
        "prerequis_en",
        "plan_cours_en",
        "langue_en",
        "limites_en",
    } <= required


def test_document_summary_normalizer_keeps_three_distinct_languages():
    fiche = document_summary._normaliser_reponse_ia(
        _payload_trilingue(),
        titre="Cours de démonstration",
        matiere="Mathématiques",
        type_document="cours",
        texte="Contenu de démonstration suffisamment long pour les tests.",
    )

    assert fiche["resume"] == "Résumé français vérifié."
    assert fiche["fiche_malagasy"]["resume"] == "Famintinana amin'ny teny malagasy."
    assert fiche["fiche_anglais"]["resume"] == "Verified English summary."
    assert fiche["fiche_anglais"]["objectif_pedagogique"] == "Understand the subject."
    assert fiche["fiche_anglais"]["notions_cles"] == ["Key topic"]
    assert fiche["fiche_anglais"]["statut"] == "generee"


def test_local_document_summary_has_explicit_english_fallback():
    fiche = document_summary._resume_local(
        "Sample course",
        "Mathematics",
        "cours",
        "Short document text is deliberately insufficient to create a complete AI summary.",
    )

    assert fiche["fiche_anglais"]["statut"] == "indisponible"
    assert "reliable English summary" in fiche["fiche_anglais"]["resume"]
