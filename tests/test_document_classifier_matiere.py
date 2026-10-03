from app.document_classifier import classifier_document
from app.models import Filiere


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
