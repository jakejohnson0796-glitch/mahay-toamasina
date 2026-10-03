from app.document_classifier import classifier_document
from app.models import Filiere, TypeDocument


def test_classification_locale_detecte_type_annee_titre_et_filiere(monkeypatch):
    monkeypatch.setattr("app.document_classifier.parametres.groq_api_key", "")

    filieres = [
        Filiere(id=1, nom="Droit"),
        Filiere(id=2, nom="Finance et Comptabilite"),
    ]

    resultat = classifier_document(
        nom_fichier="Annale_Droit_civil_2024.pdf",
        texte="Université de Toamasina\nDroit civil\nSession normale 2024",
        filieres=filieres,
        titre_fourni="",
        matiere_fourni="",
        type_fourni=None,
        annee_fournie=None,
        filiere_id_fournie=None,
    )

    assert resultat.type_document == TypeDocument.ANNALE
    assert resultat.annee == 2024
    assert resultat.filiere_id == 1
    assert "Annale" in (resultat.titre or "")
    assert resultat.source == "locale"


def test_classification_conserve_les_valeurs_fournies_quand_aucun_signal_fort(monkeypatch):
    monkeypatch.setattr("app.document_classifier.parametres.groq_api_key", "")

    filieres = [Filiere(id=7, nom="Sciences économiques")]

    resultat = classifier_document(
        nom_fichier="document.pdf",
        texte="Quelques lignes générales sans métadonnées exploitables.",
        filieres=filieres,
        titre_fourni="Mon cours",
        matiere_fourni="Économie générale",
        type_fourni=TypeDocument.COURS,
        annee_fournie=2026,
        filiere_id_fournie=7,
    )

    assert resultat.titre == "document"
    assert resultat.matiere == "Économie générale"
    assert resultat.type_document == TypeDocument.COURS
    assert resultat.annee == 2026
    assert resultat.filiere_id == 7


def test_router_expose_l_option_de_detection_auto():
    from app.routers.documents_router import upload_document

    code = upload_document.__annotations__
    assert "classification_auto" in code
    assert code["classification_auto"] is bool
