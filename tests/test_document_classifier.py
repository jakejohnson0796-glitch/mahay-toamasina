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

    assert resultat.titre == "Mon cours"
    assert resultat.matiere == "Économie générale"
    assert resultat.type_document == TypeDocument.COURS
    assert resultat.annee == 2026
    assert resultat.filiere_id == 7
    assert resultat.confiance == 0.0


def test_router_expose_l_option_de_detection_auto():
    from app.routers.documents_router import upload_document

    code = upload_document.__annotations__
    assert "classification_auto" in code
    assert code["classification_auto"] is bool


def test_detection_recupere_matiere_canonique_et_filiere_avec_une_legere_faute(monkeypatch):
    monkeypatch.setattr("app.document_classifier.parametres.groq_api_key", "")

    resultat = classifier_document(
        nom_fichier="scan_maths_2026_annale.pdf",
        texte=(
            "UNIVERSITE DE TOAMASINA\n"
            "UFR Sciences economques\n"
            "Session normale 2026\n"
            "Sujet de l'examen final"
        ),
        filieres=[Filiere(id=12, nom="Sciences économiques")],
    )

    assert resultat.matiere == "Mathématiques"
    assert resultat.type_document == TypeDocument.ANNALE
    assert resultat.annee == 2026
    assert resultat.filiere_id == 12
    assert resultat.titre is not None and "2026" not in resultat.titre


def test_titre_est_retrouve_dans_le_contenu_quand_le_nom_est_generique(monkeypatch):
    monkeypatch.setattr("app.document_classifier.parametres.groq_api_key", "")

    resultat = classifier_document(
        nom_fichier="scan_2026.pdf",
        texte=(
            "UNIVERSITE DE TOAMASINA\n"
            "FACULTE DES SCIENCES\n"
            "Analyse des fonctions et applications\n"
            "Ce cours présente les fonctions."
        ),
        filieres=[],
    )

    assert resultat.titre == "Analyse des fonctions et applications"
    assert resultat.annee == 2026



def test_annee_de_session_prime_sur_l_annee_dans_le_nom_du_fichier(monkeypatch):
    monkeypatch.setattr("app.document_classifier.parametres.groq_api_key", "")
    resultat = classifier_document(
        nom_fichier="Annale_Droit_civil_2024.pdf",
        texte=(
            "Université de Toamasina\n"
            "Matière : Droit civil\n"
            "Épreuve finale\n"
            "Session normale 2026"
        ),
        filieres=[Filiere(id=1, nom="Droit")],
    )
    assert resultat.annee == 2026


def test_annee_academique_retient_la_fin_de_la_periode():
    from app.document_classifier import _annee_depuis_texte

    assert _annee_depuis_texte("Année académique 2025-2026", "cours_2024.pdf") == 2026


def test_classifieur_reconnait_les_pluriels_des_types_documentaires():
    from app.document_classifier import _type_local

    assert _type_local("ANNALES DE MATHÉMATIQUES") == TypeDocument.ANNALE
    assert _type_local("EXAMENS ET ÉPREUVES") == TypeDocument.ANNALE
    assert _type_local("CORRIGÉS OFFICIELS") == TypeDocument.CORRIGE
    assert _type_local("FICHES DE RÉVISION") == TypeDocument.FICHE


def test_titre_ocr_ignore_les_entetes_administratifs():
    from app.document_classifier import _titre_depuis_texte

    texte = (
        "UNIVERSITÉ DE TOAMASINA\n"
        "ANNÉE UNIVERSITAIRE 2025-2026\n"
        "SESSION NORMALE 2026\n"
        "ÉPREUVE FINALE\n"
        "Analyse des fonctions et applications"
    )
    assert _titre_depuis_texte(texte) == "Analyse des fonctions et applications"


def test_alias_matiere_est_rattache_a_la_matiere_officielle_du_referentiel(monkeypatch):
    monkeypatch.setattr("app.document_classifier.parametres.groq_api_key", "")
    resultat = classifier_document(
        nom_fichier="scan_maths_2026_annale.pdf",
        texte="Session normale 2026\nSujet de l'examen final",
        filieres=[Filiere(id=22, nom="Mathématiques")],
    )
    assert resultat.matiere == "Mathématiques"
    assert resultat.filiere_id == 22


def test_score_de_confiance_ne_compte_pas_les_champs_manuels():
    resultat = classifier_document(
        nom_fichier="document.pdf",
        texte="Quelques lignes sans métadonnées suffisantes.",
        filieres=[Filiere(id=7, nom="Sciences économiques")],
        titre_fourni="Mon cours",
        matiere_fourni="Économie générale",
        type_fourni=TypeDocument.COURS,
        annee_fournie=2026,
        filiere_id_fournie=7,
    )
    assert resultat.titre == "Mon cours"
    assert resultat.matiere == "Économie générale"
    assert resultat.type_document == TypeDocument.COURS
    assert resultat.annee == 2026
    assert resultat.filiere_id == 7
    assert resultat.confiance == 0.0


def test_titre_ne_reprend_pas_une_phrase_explicative():
    from app.document_classifier import _titre_depuis_texte

    assert _titre_depuis_texte(
        "Quelques lignes générales sans métadonnées exploitables."
    ) is None
