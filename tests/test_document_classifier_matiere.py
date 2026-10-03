from app.document_classifier import classifier_document
from app.models import Filiere, TypeDocument


def test_matiere_depuis_nom_fichier_quand_ia_recopie_une_phrase(monkeypatch):
    monkeypatch.setattr(
        "app.document_classifier._classification_ia",
        lambda *args, **kwargs: {
            "titre": "algèbre",
            "matiere": "1) Si deux rangées (ou deux colonnes) d’un déterminant sont permutées",
            "type_document": "cours",
            "annee": 2026,
            "filiere_nom": "",
            "confiance": 0.91,
        },
    )

    filieres = [Filiere(id=1, nom="Mathématiques")]

    resultat = classifier_document(
        nom_fichier="Cours-algèbre.pdf",
        texte="Chapitre 1 Calcul matriciel\n1.1 Définitions et propriétés",
        filieres=filieres,
    )

    assert resultat.matiere == "algèbre"
    assert resultat.titre == "algèbre"


def test_signaux_forts_du_fichier_prioritaires_sur_un_mauvais_resultat_ia(monkeypatch):
    monkeypatch.setattr(
        "app.document_classifier._classification_ia",
        lambda *args, **kwargs: {
            "titre": "algèbre",
            "matiere": "1) Si deux rangées (ou deux colonnes) d’un déterminant sont permutées",
            "type_document": "corrige",
            "annee": 1999,
            "filiere_nom": "",
            "confiance": 0.98,
        },
    )

    filieres = [Filiere(id=1, nom="Mathématiques")]

    resultat = classifier_document(
        nom_fichier="Cours-algèbre-2026.pdf",
        texte="Chapitre 1 Calcul matriciel",
        filieres=filieres,
    )

    assert resultat.matiere == "algèbre"
    assert resultat.type_document == TypeDocument.COURS
    assert resultat.annee == 2026
