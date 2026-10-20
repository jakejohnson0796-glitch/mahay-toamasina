from datetime import datetime

import pytest
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from sqlmodel import SQLModel, Session, create_engine, select, func
from sqlalchemy.pool import StaticPool

from app import ai_queue, course_revision
from app.models import (
    Cours,
    FicheRevisionCours,
    InscriptionCours,
    RoleUtilisateur,
    Seance,
    StatutFicheRevisionCours,
    StatutSeance,
    TacheIA,
    Utilisateur,
)


def fiche_valide():
    return {
        "resume": "Les matrices permettent de représenter des systèmes linéaires.",
        "objectifs": ["Identifier une matrice", "Effectuer un produit matriciel"],
        "notions": [
            {"titre": "Matrice", "explication": "Un tableau rectangulaire de nombres.", "exemple": "Une matrice 2 × 2 a quatre coefficients."},
            {"titre": "Déterminant", "explication": "Il aide à savoir si une matrice carrée est inversible.", "exemple": "Pour une matrice 2 × 2, ad - bc."},
            {"titre": "Produit", "explication": "Les dimensions internes doivent coïncider.", "exemple": "Une matrice 2 × 3 peut multiplier une matrice 3 × 1."},
        ],
        "outils_a_retenir": [
            {"titre": "Déterminant 2 × 2", "contenu": "det(A) = ad - bc", "explication": "A = [[a,b],[c,d]]."}
        ],
        "exercices": [
            {"enonce": "Calcule le déterminant de [[2,1],[3,4]].", "difficulte": "Facile", "indice": "Calcule ad - bc.", "correction": "2×4 - 1×3 = 8 - 3 = 5.", "notion": "Déterminant"},
            {"enonce": "Pourquoi les dimensions doivent-elles coïncider pour un produit AB ?", "difficulte": "Moyen", "indice": "Compare le nombre de colonnes de A au nombre de lignes de B.", "correction": "Les dimensions internes doivent être égales pour définir chaque produit scalaire de ligne par colonne.", "notion": "Produit matriciel"},
            {"enonce": "Que signifie un déterminant nul ?", "difficulte": "Moyen", "indice": "Pense à l'inversibilité.", "correction": "La matrice carrée n'est pas inversible.", "notion": "Inversibilité"},
        ],
        "points_a_retravailler": ["Bien vérifier les dimensions avant de calculer un produit."],
        "plan_revision": [
            {"moment": "Aujourd'hui", "action": "Relire les définitions et résoudre un exercice."},
            {"moment": "Dans 2 jours", "action": "Refaire les exercices sans consulter la correction."},
            {"moment": "Dans 7 jours", "action": "Passer un quiz court pour vérifier la mémorisation."},
        ],
        "auto_evaluation": [
            {"question": "Quelle formule calcule le déterminant 2 × 2 ?", "reponse": "ad - bc."},
            {"question": "Quelle condition vérifie-t-on avant AB ?", "reponse": "Le nombre de colonnes de A égale le nombre de lignes de B."},
            {"question": "Quand une matrice carrée est-elle inversible ?", "reponse": "Lorsque son déterminant n'est pas nul."},
        ],
        "limites_sources": "Cette fiche est basée sur les notes et supports disponibles.",
    }


def test_normalise_fiche_revision_personnalisee():
    fiche = course_revision.normaliser_fiche_revision(fiche_valide())

    assert len(fiche["notions"]) == 3
    assert len(fiche["exercices"]) == 3
    assert [x["moment"] for x in fiche["plan_revision"]] == [
        "Aujourd'hui",
        "Dans 2 jours",
        "Dans 7 jours",
    ]

    notation = course_revision._normaliser_notation_math(r"\frac{1}{2} \times \sqrt{9} \leq \Delta")
    assert notation == "(1)/(2) * sqrt(9) <= Delta"
    assert course_revision._texte_pdf_compatible("√9 ≤ 3; Δ ≠ 0; x²") == "sqrt9 <= 3; Delta != 0; x^2"


def test_refuse_fiche_revision_incomplete():
    donnees = fiche_valide()
    donnees["exercices"] = []
    with pytest.raises(ValueError):
        course_revision.normaliser_fiche_revision(donnees)


def test_exports_pdf_et_docx_non_vides():
    fiche = course_revision.normaliser_fiche_revision(fiche_valide())
    cours = Cours(id=4, nom="Algèbre", matiere="Mathématiques", niveau="L1", professeur_id=7)
    seance = Seance(
        id=12,
        cours_id=4,
        titre="Matrices et déterminants",
        nom_salle_livekit="mahay-test-room",
        statut=StatutSeance.TERMINEE,
        date_fin_reelle=datetime(2026, 10, 20, 12, 0, 0),
    )

    # Les symboles mathématiques reçus par l'IA ne doivent pas faire échouer ReportLab.
    fiche["notions"][0]["explication"] = "Vérifie √9 ≤ 3 et Δ ≠ 0."
    pdf = course_revision.generer_pdf(fiche, cours, seance, "Étudiant Test")
    docx = course_revision.generer_docx(fiche, cours, seance, "Étudiant Test")

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1200
    assert docx.startswith(b"PK")
    assert len(docx) > 1200


def test_planification_est_idempotente_et_reservee_aux_etudiants_inscrits(monkeypatch, tmp_path):
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'fiches-revision.db'}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr(ai_queue, "engine", test_engine)
    monkeypatch.setattr(ai_queue, "notifier_tache", lambda _task_id: True)

    with Session(test_engine) as session:
        professeur = Utilisateur(
            nom="Professeur Test",
            telephone="+261340000001",
            mot_de_passe_hash="test-hash",
            role=RoleUtilisateur.PROFESSEUR,
        )
        etudiant = Utilisateur(
            nom="Étudiant Test",
            telephone="+261340000002",
            mot_de_passe_hash="test-hash",
            role=RoleUtilisateur.ETUDIANT,
        )
        session.add(professeur)
        session.add(etudiant)
        session.commit()
        session.refresh(professeur)
        session.refresh(etudiant)

        cours = Cours(
            nom="Algèbre",
            matiere="Mathématiques",
            niveau="L1",
            professeur_id=professeur.id,
        )
        session.add(cours)
        session.commit()
        session.refresh(cours)

        seance = Seance(
            cours_id=cours.id,
            titre="Matrices",
            nom_salle_livekit="mahay-test-room-2",
            statut=StatutSeance.TERMINEE,
            date_fin_reelle=datetime.utcnow(),
        )
        session.add(seance)
        session.add(InscriptionCours(cours_id=cours.id, utilisateur_id=etudiant.id))
        session.commit()
        session.refresh(seance)

        cours_id = cours.id
        seance_id = seance.id
        etudiant_id = etudiant.id

    fiche_id_1 = ai_queue.planifier_fiche_revision_cours(seance_id, etudiant_id)
    fiche_id_2 = ai_queue.planifier_fiche_revision_cours(seance_id, etudiant_id)

    assert fiche_id_1 == fiche_id_2
    with Session(test_engine) as session:
        assert session.exec(select(func.count()).select_from(FicheRevisionCours)).one() == 1
        taches = session.exec(
            select(TacheIA).where(
                TacheIA.type_tache == ai_queue.TYPE_FICHE_REVISION_COURS
            )
        ).all()
        assert len(taches) == 1
        assert taches[0].fiche_revision_cours_id == fiche_id_1
        fiche = session.get(FicheRevisionCours, fiche_id_1)
        assert fiche is not None
        assert fiche.statut == StatutFicheRevisionCours.EN_ATTENTE

    with Session(test_engine) as session:
        non_inscrit = Utilisateur(
            nom="Non inscrit",
            telephone="+261340000003",
            mot_de_passe_hash="test-hash",
            role=RoleUtilisateur.ETUDIANT,
        )
        session.add(non_inscrit)
        session.commit()
        session.refresh(non_inscrit)
        non_inscrit_id = non_inscrit.id

    assert ai_queue.planifier_fiche_revision_cours(seance_id, non_inscrit_id) is None

def test_template_classe_detail_compile_avec_la_fiche_personnalisee():
    templates_dir = Path(__file__).resolve().parents[1] / "app" / "templates"
    source = (templates_dir / "classe_detail.html").read_text(encoding="utf-8")
    template = Environment(loader=FileSystemLoader(str(templates_dir))).get_template("classe_detail.html")

    assert template.name == "classe_detail.html"
    assert "fiches_revision_par_seance" in source
    assert "/telecharger/pdf" in source
    assert "/telecharger/docx" in source
