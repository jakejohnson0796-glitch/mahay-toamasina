from datetime import datetime
import io
import json
from types import SimpleNamespace

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
    ProgressionNotion,
    RoleUtilisateur,
    Seance,
    SessionTuteur,
    StatutFicheRevisionCours,
    StatutSeance,
    StatutTacheIA,
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
        "erreurs_frequentes": [
            {"erreur": "Confondre lignes et colonnes", "pourquoi": "Cela inverse les dimensions d'une matrice.", "comment_eviter": "Compte séparément les lignes puis les colonnes."},
            {"erreur": "Inverser les termes du déterminant", "pourquoi": "Le signe du résultat peut changer.", "comment_eviter": "Applique la formule ad - bc dans le même ordre."},
            {"erreur": "Multiplier des matrices sans vérifier les dimensions", "pourquoi": "Le produit peut ne pas être défini.", "comment_eviter": "Vérifie que les colonnes de A égalent les lignes de B."},
        ],
        "outils_a_retenir": [
            {"titre": "Déterminant 2 × 2", "contenu": "det(A) = ad - bc", "explication": "A = [[a,b],[c,d]]."}
        ],
        "exercices": [
            {"enonce": "Calcule le déterminant de [[2,1],[3,4]].", "difficulte": "Facile", "indice": "Calcule ad - bc.", "correction": "2×4 - 1×3 = 8 - 3 = 5.", "notion": "Déterminant"},
            {"enonce": "Pourquoi les dimensions doivent-elles coïncider pour un produit AB ?", "difficulte": "Moyen", "indice": "Compare le nombre de colonnes de A au nombre de lignes de B.", "correction": "Les dimensions internes doivent être égales pour définir chaque produit scalaire de ligne par colonne.", "notion": "Produit matriciel"},
            {"enonce": "Que signifie un déterminant nul ?", "difficulte": "Difficile", "indice": "Pense à l'inversibilité.", "correction": "La matrice carrée n'est pas inversible.", "notion": "Inversibilité"},
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


def test_prompts_fiches_revision_prescrivent_une_meilleure_pedagogie_et_un_latex_sain():
    contexte = {"cours": {}, "seance": {}, "source_document": {"contenu_extrait": "Matrice de type (2, 3)."}}
    prompt_personnel = course_revision._texte_ia_non_fiable(contexte)
    prompt_document = course_revision._texte_ia_document(
        {"source_document": {"contenu_extrait": "Matrice de type (2, 3)."}}
    )

    for prompt in (prompt_personnel, prompt_document):
        assert "erreurs_frequentes" in prompt
        assert "LaTeX" in prompt
        assert r"\begin{pmatrix}" in prompt
        assert "Facile" in prompt and "Difficile" in prompt


def test_normalisation_fiche_preserve_le_latex_pour_katex():
    donnees = fiche_valide()
    formule = r"Calcul : \(A=\begin{pmatrix}1&2\\3&4\end{pmatrix}\) et \(\det(A)=\frac{1}{2}\)."
    donnees["resume"] = formule
    donnees["notions"][0]["explication"] = formule

    fiche = course_revision.normaliser_fiche_revision(donnees)

    assert r"\begin{pmatrix}" in fiche["resume"]
    assert r"\\3&4" in fiche["resume"]
    assert r"\frac{1}{2}" in fiche["notions"][0]["explication"]
    assert "beginpmatrix1&2" not in fiche["resume"]


def test_normalisation_fiche_preserve_les_sequences_latex_legacy_reparables():
    # Le caractère contrôle est un vestige du décodage JSON de « \begin ».
    ancienne_formule = "Matrice " + "\x08egin{pmatrix}1&2\\\\3&4\\end{pmatrix}"
    normalisee = course_revision._normaliser_texte(ancienne_formule)

    assert "\x08egin{pmatrix}" in normalisee
    assert "egin{pmatrix}" in normalisee


def test_export_math_convertit_une_matrice_en_lignes_lisibles():
    notation = course_revision._normaliser_notation_math(
        r"A=\begin{pmatrix}1&2\\3&4\end{pmatrix}, \det(A)=\frac{1}{2}"
    )
    assert "A=" in notation
    assert "[[1, 2], [3, 4]]" in notation
    assert "beginpmatrix" not in notation
    assert "end{pmatrix}" not in notation


def test_fiche_valide_respecte_le_contrat_pedagogique_strict():
    fiche = course_revision.normaliser_fiche_revision(fiche_valide(), exiger_qualite=True)
    assert len(fiche["erreurs_frequentes"]) == 3
    assert {exercice["difficulte"] for exercice in fiche["exercices"]} == {
        "Facile", "Moyen", "Difficile"
    }


def test_validation_qualite_refuse_les_exercices_repetes_et_niveaux_absents():
    donnees = fiche_valide()
    donnees["exercices"][2]["difficulte"] = "Moyen"
    with pytest.raises(ValueError, match="trois niveaux"):
        course_revision.normaliser_fiche_revision(donnees, exiger_qualite=True)


def test_fiche_documentaire_est_personnalisee_par_etudiant_sans_fuite_de_donnees():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)

    with Session(test_engine) as session:
        etudiant_a = Utilisateur(
            nom="Étudiant A",
            telephone="+261340000301",
            mot_de_passe_hash="hash-a",
            role=RoleUtilisateur.ETUDIANT,
        )
        etudiant_b = Utilisateur(
            nom="Étudiant B",
            telephone="+261340000302",
            mot_de_passe_hash="hash-b",
            role=RoleUtilisateur.ETUDIANT,
        )
        session.add_all([etudiant_a, etudiant_b])
        session.commit()
        session.refresh(etudiant_a)
        session.refresh(etudiant_b)

        progression_a = ProgressionNotion(
            utilisateur_id=etudiant_a.id,
            matiere="Mathématiques",
            niveau="L1",
            notion="Déterminant d'ordre 2",
            nb_questions=6,
            nb_reussites=2,
            nb_erreurs=4,
            score_maitrise=28,
            maitrise_confirmee=False,
            prochaine_revision_le=datetime.utcnow(),
        )
        progression_b = ProgressionNotion(
            utilisateur_id=etudiant_b.id,
            matiere="Mathématiques",
            niveau="L1",
            notion="NOTION PRIVÉE DE L'ÉTUDIANT B",
            nb_questions=6,
            nb_reussites=1,
            nb_erreurs=5,
            score_maitrise=18,
            maitrise_confirmee=False,
        )
        session.add_all([progression_a, progression_b])
        session.commit()
        session.refresh(progression_a)

        session.add(
            SessionTuteur(
                utilisateur_id=etudiant_a.id,
                progression_id=progression_a.id,
                notion=progression_a.notion,
                question="Pourquoi faut-il soustraire les deux produits ?",
                comprehension_reponse="J'additionne les deux produits.",
                comprehension_feedback="Le signe du second produit est à revoir.",
                comprehension_validee=False,
                explication="Explication de test.",
                exemple="Exemple de test.",
                exercice="Exercice de test.",
                correction="Correction de test.",
            )
        )
        session.commit()

        document = SimpleNamespace(
            id=700,
            filiere_id=None,
            matiere="Mathématiques",
            titre="Matrices et déterminants",
        )
        fiche_source = course_revision.normaliser_fiche_revision(fiche_valide())
        source_json_avant = json.dumps(fiche_source, ensure_ascii=False)

        fiche_a = course_revision.personnaliser_fiche_revision_document(
            session, document, etudiant_a.id, fiche_source
        )
        fiche_b = course_revision.personnaliser_fiche_revision_document(
            session, document, etudiant_b.id, fiche_source
        )

    profil_a = fiche_a["profil_personnalise"]
    profil_b = fiche_b["profil_personnalise"]
    assert profil_a["mode"] == "Adaptée à ton parcours"
    assert profil_a["priorites"][0]["notion"] == "Déterminant d'ordre 2"
    assert "NOTION PRIVÉE DE L'ÉTUDIANT B" not in json.dumps(fiche_a, ensure_ascii=False)
    assert "Déterminant d'ordre 2" not in json.dumps(fiche_b, ensure_ascii=False)
    assert "Tuteur IA" in profil_a["conseil_tuteur"]
    assert "aujourd'hui" in fiche_a["plan_revision"][0]["action"].casefold()
    assert "profil_personnalise" not in fiche_source
    assert json.dumps(fiche_source, ensure_ascii=False) == source_json_avant


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
    assert course_revision._texte_pdf_compatible("√9 ≤ 3; Δ ≠ 0; x²") == "sqrt(9) <= 3; Delta != 0; x^2"


@pytest.mark.parametrize(
    "erreur_initiale",
    [
        "json_validate_failed: jsonschema /exercices/0 missing properties: 'notion'",
        "max completion tokens reached before generating a valid document: output was truncated and is missing required content",
    ],
)
def test_recupere_une_fiche_si_notion_manquante_ou_sortie_tronquee(monkeypatch, erreur_initiale):
    donnees = fiche_valide()
    for exercice in donnees["exercices"]:
        exercice.pop("notion", None)

    class FauxCompletion:
        def create(self, **kwargs):
            schema = kwargs["response_format"]["json_schema"]["schema"]
            assert "notion" not in schema["properties"]["exercices"]["items"]["properties"]
            message = SimpleNamespace(content=json.dumps(donnees, ensure_ascii=False))
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class FauxGroq:
        def __init__(self, api_key):
            self.chat = SimpleNamespace(completions=FauxCompletion())

    monkeypatch.setattr(course_revision, "Groq", FauxGroq)
    monkeypatch.setattr(course_revision.parametres, "groq_api_key", "cle-test")
    monkeypatch.setattr(course_revision.parametres, "groq_model", "openai/gpt-oss-120b")

    appels = {"nombre": 0}

    def appel_avec_erreur_puis_reprise(_provider, operation):
        appels["nombre"] += 1
        if appels["nombre"] == 1:
            raise RuntimeError(erreur_initiale)
        return operation()

    monkeypatch.setattr(
        course_revision.ai_ensemble.cost_controller,
        "call",
        appel_avec_erreur_puis_reprise,
    )

    fiche = course_revision._generer_contenu_ia(
        {"source_document": {"contenu_extrait": "Cours sur les matrices et déterminants."}},
        mode_document=True,
    )

    assert appels["nombre"] == 2
    assert fiche["exercices"][0]["notion"] == "Déterminant"
    assert all(exercice["notion"] for exercice in fiche["exercices"])
    assert course_revision.MAX_COMPLETION_TOKENS == 6000


def test_schema_de_secours_ne_requiert_pas_la_notion_de_chaque_exercice():
    schema = course_revision._schema_fiche_revision_sans_notion()

    assert "notion" not in schema["properties"]["exercices"]["items"]["properties"]
    assert "notion" not in schema["properties"]["exercices"]["items"]["required"]
    assert "erreurs_frequentes" in schema["required"]
    assert "notion" in course_revision._SCHEMA_FICHE["properties"]["exercices"]["items"]["properties"]


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
    fiche["notions"][0]["explication"] = r"Vérifie \(A=\begin{pmatrix}1&2\\3&4\end{pmatrix}\) et \(\det(A)\ne 0\)."
    pdf = course_revision.generer_pdf(fiche, cours, seance, "Étudiant Test")
    docx = course_revision.generer_docx(fiche, cours, seance, "Étudiant Test")

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1200
    assert docx.startswith(b"PK")
    assert len(docx) > 1200

    # Le DOCX ne doit pas réintroduire les environnements bruts qui sont réservés
    # au navigateur : il doit présenter la matrice sous forme de lignes lisibles.
    word = course_revision.WordDocument(io.BytesIO(docx))
    texte_word = "\\n".join(paragraphe.text for paragraphe in word.paragraphs)
    assert "begin{pmatrix}" not in texte_word
    assert "[[1, 2], [3, 4]]" in texte_word
    assert "ne 0" not in texte_word


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
        fiche = session.get(FicheRevisionCours, fiche_id_1)
        tache = session.exec(
            select(TacheIA).where(
                TacheIA.type_tache == ai_queue.TYPE_FICHE_REVISION_COURS
            )
        ).one()
        fiche.statut = StatutFicheRevisionCours.TERMINEE
        fiche.contenu_json = json.dumps(fiche_valide(), ensure_ascii=False)
        fiche.version_generation = "v3"
        tache.statut = StatutTacheIA.TERMINEE
        tache.terminee_le = datetime.utcnow()
        session.add(fiche)
        session.add(tache)
        session.commit()

    # Une fiche finie sous l'ancien générateur est régénérée lors de sa prochaine
    # consultation, mais reste idempotente : la même tâche durable est réutilisée.
    assert ai_queue.planifier_fiche_revision_cours(seance_id, etudiant_id) == fiche_id_1
    with Session(test_engine) as session:
        fiche = session.get(FicheRevisionCours, fiche_id_1)
        assert fiche.version_generation == "v3"
        assert fiche.statut == StatutFicheRevisionCours.EN_ATTENTE
        taches = session.exec(
            select(TacheIA).where(TacheIA.type_tache == ai_queue.TYPE_FICHE_REVISION_COURS)
        ).all()
        assert len(taches) == 1
        assert taches[0].statut == StatutTacheIA.EN_ATTENTE

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

def test_templates_fiche_revision_compile_et_exposent_les_formats():
    templates_dir = Path(__file__).resolve().parents[1] / "app" / "templates"
    environnement = Environment(loader=FileSystemLoader(str(templates_dir)))
    source_cours = (templates_dir / "classe_detail.html").read_text(encoding="utf-8")
    source_lecture = (templates_dir / "classe_revision.html").read_text(encoding="utf-8")
    cours_template = environnement.get_template("classe_detail.html")
    lecture_template = environnement.get_template("classe_revision.html")

    assert cours_template.name == "classe_detail.html"
    assert lecture_template.name == "classe_revision.html"
    assert "fiches_revision_par_seance" in source_cours
    assert "Consulter la fiche" in source_cours
    assert "/telecharger/pdf" in source_cours
    assert "/telecharger/docx" in source_cours
    assert "data-rendu" in source_lecture
    assert "J’ai essayé" in source_lecture
    assert "fiche_contenu.erreurs_frequentes" in source_lecture
    assert "erreurs_frequentes" in (templates_dir / "document_revision.html").read_text(encoding="utf-8")
    assert "fiche_contenu.get(\"profil_personnalise\")" in source_lecture
    assert "profil.get(\"priorites\")" in source_lecture
    assert "/telecharger/pdf" in source_lecture
    assert "/telecharger/docx" in source_lecture

def test_contexte_ia_est_borne_sans_effacer_la_personnalisation():
    contexte = {
        "cours": {"nom": "Algèbre", "matiere": "Mathématiques", "niveau": "L1", "description": "Cours " * 500},
        "seance": {
            "titre": "Matrices",
            "description": "Notes " * 600,
            "notes_tableau_blanc": ["Note importante " * 90 for _ in range(28)],
        },
        "consignes_devoirs": [{"titre": f"Devoir {n}", "consigne": "Consigne " * 90} for n in range(6)],
        "supports_academiques_approuves": [
            {"titre": f"Support {n}", "niveau_source": "L1", "type": "cours", "resume": "Résumé " * 150}
            for n in range(3)
        ],
        "profil_individuel": {
            "notions_a_retravailler": [
                {"notion": f"Notion fragile {n}", "score_maitrise": 20 + n, "questions_observees": 10, "erreurs_observees": 8}
                for n in range(6)
            ],
            "resultats_quiz_recents": [{"score": 2, "questions": 5, "date": "20/10/2026"} for _ in range(4)],
        },
        "limites_sources": "Transcription non disponible. " * 200,
    }

    borne = course_revision._borner_contexte(contexte)

    import json
    assert len(json.dumps(borne, ensure_ascii=False, separators=(",", ":"))) <= course_revision.MAX_SOURCE_CHARS
    assert borne["profil_individuel"]["notions_a_retravailler"]
    assert borne["cours"]["matiere"] == "Mathématiques"


def test_normalise_niveaux_academiques_usuels():
    assert course_revision._niveau_cle("Licence 1") == "l1"
    assert course_revision._niveau_cle("L1") == "l1"
    assert course_revision._niveau_cle("Master 2") == "m2"

def test_personnalisation_ne_croise_pas_les_niveaux_academiques():
    assert course_revision._niveaux_compatibles("Licence 1", "L1")
    assert course_revision._niveaux_compatibles("L1", None)
    assert not course_revision._niveaux_compatibles("L1", "L3")

def test_normalise_alias_matiere_pour_personnalisation():
    assert course_revision._matiere_cle("Maths") == "mathematiques"
    assert course_revision._matiere_cle("Mathématique") == "mathematiques"
    assert course_revision._matiere_cle("Info") == "informatique"



def test_fiche_de_cours_integre_le_tutorat_recent_de_son_etudiant(monkeypatch):
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)

    with Session(test_engine) as session:
        professeur = Utilisateur(
            nom="Professeur Mémoire",
            telephone="+261340000201",
            mot_de_passe_hash="prof-hash",
            role=RoleUtilisateur.PROFESSEUR,
        )
        etudiant = Utilisateur(
            nom="Étudiant Mémoire",
            telephone="+261340000202",
            mot_de_passe_hash="student-hash",
            role=RoleUtilisateur.ETUDIANT,
        )
        autre = Utilisateur(
            nom="Autre Étudiant",
            telephone="+261340000203",
            mot_de_passe_hash="other-hash",
            role=RoleUtilisateur.ETUDIANT,
        )
        session.add_all([professeur, etudiant, autre])
        session.commit()
        session.refresh(professeur)
        session.refresh(etudiant)
        session.refresh(autre)

        cours = Cours(
            nom="Algèbre linéaire",
            matiere="Mathématiques",
            niveau="L1",
            professeur_id=professeur.id,
            description="Étude des matrices et déterminants.",
        )
        session.add(cours)
        session.commit()
        session.refresh(cours)

        seance = Seance(
            cours_id=cours.id,
            titre="Déterminants",
            description="Calcul d'un déterminant d'ordre deux.",
            nom_salle_livekit="revision-memory-room",
            statut=StatutSeance.TERMINEE,
            date_fin_reelle=datetime.utcnow(),
        )
        session.add(seance)
        session.commit()
        session.refresh(seance)

        progression = ProgressionNotion(
            utilisateur_id=etudiant.id,
            matiere="Mathématiques",
            niveau="L1",
            notion="Déterminant d'ordre 2",
            nb_questions=3,
            nb_erreurs=2,
            score_maitrise=35,
        )
        progression_autre = ProgressionNotion(
            utilisateur_id=autre.id,
            matiere="Mathématiques",
            niveau="L1",
            notion="Déterminant d'ordre 2",
            nb_questions=3,
            nb_erreurs=2,
            score_maitrise=35,
        )
        session.add_all([progression, progression_autre])
        session.commit()
        session.refresh(progression)
        session.refresh(progression_autre)

        session.add_all([
            SessionTuteur(
                utilisateur_id=etudiant.id,
                progression_id=progression.id,
                notion=progression.notion,
                question="Pourquoi le second produit est-il soustrait ?",
                comprehension_reponse="J'additionne les deux produits.",
                comprehension_feedback="Il faut revoir le signe du second produit.",
                comprehension_validee=False,
                explication="Explication.",
                exemple="Exemple.",
                exercice="Exercice.",
                correction="Correction.",
            ),
            SessionTuteur(
                utilisateur_id=autre.id,
                progression_id=progression_autre.id,
                notion=progression_autre.notion,
                question="CONVERSATION PRIVÉE D'UN AUTRE ÉTUDIANT.",
                comprehension_reponse="NE PAS COPIER CETTE RÉPONSE.",
                comprehension_feedback="Retour d'un autre compte.",
                comprehension_validee=False,
                explication="Explication.",
                exemple="Exemple.",
                exercice="Exercice.",
                correction="Correction.",
            ),
        ])
        session.commit()

        fiche = FicheRevisionCours(
            cours_id=cours.id,
            seance_id=seance.id,
            utilisateur_id=etudiant.id,
        )
        contexte, sources = course_revision._collecter_sources(session, fiche)

    interactions = contexte["profil_individuel"]["interactions_tuteur_recentes"]
    assert len(interactions) == 1
    assert interactions[0]["question"] == "Pourquoi le second produit est-il soustrait ?"
    assert interactions[0]["etat_comprehension"] == "comprehension a retravailler"
    assert sources["personnalisation_tuteur"] is True
    assert "CONVERSATION PRIVÉE D'UN AUTRE ÉTUDIANT." not in str(contexte)
