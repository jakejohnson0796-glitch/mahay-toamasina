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
    assert fiche["fiche_malagasy"]["statut"] == "indisponible"
    assert "teny malagasy" in fiche["fiche_malagasy"]["resume"]


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
        "limites": "",
        "resume_mg": "Ity lesona ity dia manazava ny asa derivative sy ny fampiasana azy.",
        "objectif_pedagogique_mg": "Hahay handika sy hanao kajy derivative tsotra.",
        "type_cours_mg": "Lesona ara-teoria",
        "niveau_cible_mg": "Tsy voalaza mazava ao amin'ny tahirin-kevitra",
        "notions_cles_mg": ["Derivative", "Asa azo dériver-na", "Derivative"],
        "competences_visees_mg": ["Manao kajy derivative"],
        "prerequis_mg": ["Asa mahazatra"],
        "plan_cours_mg": ["Famaritana", "Fitsipika kajy"],
        "langue_mg": "Frantsay",
        "limites_mg": "",
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
    assert fiche["fiche_malagasy"]["statut"] == "generee"
    assert "derivative" in fiche["fiche_malagasy"]["resume"].lower()
    assert len(fiche["fiche_malagasy"]["notions_cles"]) == 2



def test_traduction_fiche_historique_vers_malagasy(monkeypatch):
    payload = {
        "resume": "Ity famintinana ity dia amin'ny teny malagasy.",
        "objectif_pedagogique": "Hahay hamantatra ny hevi-dehibe.",
        "type_cours": "Lesona",
        "niveau_cible": "Ambaratonga tsy voalaza",
        "notions_cles": ["Hevi-dehibe"],
        "competences_visees": ["Mamakafaka"],
        "prerequis": ["Fahalalana fototra"],
        "plan_cours": ["Fampidirana"],
        "langue": "Frantsay",
        "limites": "",
    }
    message = SimpleNamespace(
        tool_calls=[SimpleNamespace(function=SimpleNamespace(arguments=json.dumps(payload, ensure_ascii=False)))]
    )
    completion = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    faux_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kwargs: completion)
        )
    )
    monkeypatch.setattr("app.document_summary._client_ia", lambda: faux_client)
    from app.document_summary import traduire_fiche_existante_malagasy

    resultat = traduire_fiche_existante_malagasy({
        "resume": "Ce cours présente les notions essentielles.",
        "objectif_pedagogique": "Comprendre les notions essentielles.",
        "type_cours": "Support de cours",
        "niveau_cible": "L1",
        "notions_cles": ["Notion"],
        "competences_visees": ["Analyser"],
        "prerequis": ["Bases"],
        "plan_cours": ["Introduction"],
        "langue": "Français",
        "limites": "",
    })
    assert resultat["statut"] == "generee"
    assert resultat["resume"] == payload["resume"]
    assert resultat["langue"] == "Frantsay"


def test_fiches_documentaires_protegent_les_deux_langues_et_se_synchronisent():
    from pathlib import Path

    racine = Path(__file__).resolve().parents[1]
    listing = (racine / "app" / "templates" / "documents_list.html").read_text(encoding="utf-8")
    moderation = (racine / "app" / "templates" / "moderation_document_preview.html").read_text(encoding="utf-8")
    dictionnaire = (racine / "app" / "static" / "js" / "langue.js").read_text(encoding="utf-8")

    assert 'data-fiche-lang="fr"' in listing and 'data-fiche-lang="mg"' in listing
    assert 'data-no-translate' in listing
    assert 'resume_ia_mg' in listing and 'fiches_documents_mg' in listing
    assert 'data-fiche-lang="fr"' in moderation and 'data-fiche-lang="mg"' in moderation
    assert 'fiche_document_mg' in moderation
    assert '"Résumé et fiche pédagogique": "Famintinana sy mombamomba ny lesona"' in dictionnaire
