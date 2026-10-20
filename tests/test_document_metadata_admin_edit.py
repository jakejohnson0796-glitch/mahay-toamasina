from app.models import TypeDocument
from app.routers.documents_router import _normaliser_metadonnees_document


def test_normalise_metadonnees_document_admin():
    donnees, erreur = _normaliser_metadonnees_document(
        titre="  Corrigé   d'algèbre ",
        matiere="  Mathématiques   générales ",
        type_document="corrige",
        annee="2024",
        filiere_id="17",
    )

    assert erreur is None
    assert donnees == {
        "titre": "Corrigé d'algèbre",
        "matiere": "Mathématiques générales",
        "type_document": TypeDocument.CORRIGE,
        "annee": 2024,
        "filiere_id": 17,
    }


def test_refuse_metadonnees_document_incompletes_ou_invalides():
    cas_invalides = [
        {"titre": " ", "matiere": "Maths", "type_document": "cours", "annee": "2024", "filiere_id": "1"},
        {"titre": "Cours", "matiere": "", "type_document": "cours", "annee": "2024", "filiere_id": "1"},
        {"titre": "Cours", "matiere": "Maths", "type_document": "inconnu", "annee": "2024", "filiere_id": "1"},
        {"titre": "Cours", "matiere": "Maths", "type_document": "cours", "annee": "abc", "filiere_id": "1"},
        {"titre": "Cours", "matiere": "Maths", "type_document": "cours", "annee": "2024", "filiere_id": ""},
    ]

    for valeurs in cas_invalides:
        donnees, erreur = _normaliser_metadonnees_document(**valeurs)
        assert donnees is None
        assert erreur
