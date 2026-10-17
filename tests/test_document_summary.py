import json
from types import SimpleNamespace

from app.document_summary import generer_fiche_pedagogique


def test_sans_ia_fiche_provisoire_ne_invente_pas_le_niveau(monkeypatch):
    monkeypatch.setattr("app.document_summary._client_ia", lambda: None)
    fiche = generer_fiche_pedagogique(
        nom_fichier="Cours_algebre.pdf",
        titre="Algèbre linéaire",
        matiere="Mathématiques",
        type_document="cours",
        annee=2024,
        filiere="Mathématiques",
        texte="",
    )
    assert fiche["statut"] == "insuffisante"
    assert fiche["source"] == "local"
    assert "niveau non déterminé" in fiche["niveau_cible"].lower()
    assert fiche["notions_cles"] == []
    assert "pas pu être extrait" in fiche["resume"]


def test_fallback_restitue_un_apercu_provisoire_du_texte(monkeypatch):
    monkeypatch.setattr("app.document_summary._client_ia", lambda: None)
    fiche = generer_fiche_pedagogique(
        nom_fichier="TD_matrices.pdf",
        titre="Matrices",
        matiere="Algèbre",
        type_document="cours",
        annee=2025,
        filiere="Sciences",
        texte=(
            "Séance de TD : comprendre les opérations sur les matrices.\n"
            "Les étudiants calculent le produit matriciel et déterminent le rang.\n"
            "Des exercices permettent de vérifier les propriétés des matrices carrées."
        ),
    )
    assert fiche["statut"] == "provisoire"
    assert "Aperçu provisoire" in fiche["resume"]
    assert "produit matriciel" in fiche["resume"]
    assert fiche["type_cours"] == "Travaux dirigés (TD)"


def test_normalisation_reponse_ia_liste_et_objectif(monkeypatch):
    payload = {
        "resume": "Ce cours présente les fonctions dérivables et leurs applications.",
        "objectif_pedagogique": "Savoir interpréter une dérivée et calculer une dérivée simple.",
        "type_cours": "Cours théorique",
        "niveau_cible": "Non indiqué dans le document",
        "notions_cles": ["Dérivée", "Fonction dérivable", "Dérivée"],
        "competences_visees": ["Calculer une dérivée"],
        "prerequis": ["Fonctions usuelles"],
        "plan_cours": ["Définition", "Règles de calcul"],
        "langue": "Français",
        "confiance": 0.91,
    }
    message = SimpleNamespace(
        tool_calls=[SimpleNamespace(function=SimpleNamespace(arguments=json.dumps(payload, ensure_ascii=False)))]
    )
    completion = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    faux_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: completion)))
    monkeypatch.setattr("app.document_summary._client_ia", lambda: faux_client)
    fiche = generer_fiche_pedagogique(
        nom_fichier="derivees.pdf",
        titre="Dérivées",
        matiere="Mathématiques",
        type_document="cours",
        annee=2025,
        filiere="Sciences",
        texte=("Les fonctions dérivables sont au programme de ce support. " * 10),
    )
    assert fiche["source"] == "ia"
    assert fiche["statut"] == "generee"
    assert fiche["objectif_pedagogique"].startswith("Savoir interpréter")
    assert len(fiche["notions_cles"]) == 2
    assert fiche["confiance"] == 0.91
