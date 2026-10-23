from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import json

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select, func
from jinja2 import Environment, FileSystemLoader

from app import ai_queue, course_revision
from app.models import (
    Document,
    FicheRevisionDocument,
    ProgressionNotion,
    Notification,
    RoleUtilisateur,
    StatutDocument,
    StatutFicheRevisionDocument,
    StatutTacheIA,
    TacheIA,
    TypeDocument,
    TypeNotification,
    Utilisateur,
)


def fixture_fiche():
    return {
        "resume": "Le cours présente les opérations sur les matrices.",
        "objectifs": ["Reconnaître une matrice", "Calculer un déterminant simple"],
        "notions": [
            {"titre": "Matrice", "explication": "Un tableau rectangulaire de coefficients.", "exemple": "Une matrice 2 × 2 contient quatre coefficients."},
            {"titre": "Déterminant", "explication": "Pour une matrice 2 × 2, det(A) = ad - bc.", "exemple": "Pour [[2,1],[3,4]], le déterminant vaut 5."},
            {"titre": "Produit matriciel", "explication": "Le nombre de colonnes de la première matrice doit correspondre au nombre de lignes de la seconde.", "exemple": "Une matrice 2 × 3 peut multiplier une matrice 3 × 1."},
        ],
        "outils_a_retenir": [
            {"titre": "Déterminant 2 × 2", "contenu": "det(A) = ad - bc", "explication": "A = [[a,b],[c,d]]."}
        ],
        "exercices": [
            {"enonce": "Calcule le déterminant de [[2,1],[3,4]].", "difficulte": "Facile", "indice": "Calcule ad - bc.", "correction": "2×4 - 1×3 = 8 - 3 = 5.", "notion": "Déterminant"},
            {"enonce": "Vérifie les dimensions avant le produit AB.", "difficulte": "Moyen", "indice": "Compare les dimensions internes.", "correction": "Le nombre de colonnes de A doit être égal au nombre de lignes de B.", "notion": "Produit matriciel"},
            {"enonce": "Que signifie un déterminant nul ?", "difficulte": "Moyen", "indice": "Pense à l'inversibilité.", "correction": "La matrice carrée n'est pas inversible.", "notion": "Inversibilité"},
        ],
        "points_a_retravailler": ["Vérifier les dimensions avant un produit matriciel."],
        "plan_revision": [
            {"moment": "Aujourd'hui", "action": "Relire les définitions et résoudre un exercice."},
            {"moment": "Dans 2 jours", "action": "Refaire les exercices sans consulter les corrections."},
            {"moment": "Dans 7 jours", "action": "Passer un quiz court."},
        ],
        "auto_evaluation": [
            {"question": "Quelle formule calcule le déterminant 2 × 2 ?", "reponse": "ad - bc."},
            {"question": "Quelle condition vérifier pour AB ?", "reponse": "Le nombre de colonnes de A égale le nombre de lignes de B."},
            {"question": "Quand une matrice carrée est-elle inversible ?", "reponse": "Lorsque son déterminant n'est pas nul."},
        ],
        "limites_sources": "Fiche basée sur le texte extrait du document de cours approuvé.",
    }


def moteur_sqlite():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def creer_document(session, *, statut=StatutDocument.APPROUVE, type_document=TypeDocument.COURS):
    utilisateur = Utilisateur(
        nom="Déposant de test",
        telephone="+261340099991",
        mot_de_passe_hash="test-hash",
        role=RoleUtilisateur.ETUDIANT,
    )
    session.add(utilisateur)
    session.commit()
    session.refresh(utilisateur)

    document = Document(
        reference="TEST-COURS-AUTO-0001",
        titre="Algèbre linéaire — matrices",
        matiere="Mathématiques",
        type_document=type_document,
        annee=2026,
        filiere_id=777,
        uploader_id=utilisateur.id,
        chemin_fichier="/tmp/cours-source.pdf",
        statut=statut,
        resume_ia="Le document porte sur les matrices.",
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return document, utilisateur


def test_planifie_une_fiche_une_seule_fois_pour_un_cours_approuve(monkeypatch):
    engine = moteur_sqlite()
    monkeypatch.setattr(ai_queue, "engine", engine)
    monkeypatch.setattr(ai_queue, "notifier_tache", lambda _task_id: True)

    with Session(engine) as session:
        document, _ = creer_document(session)
        document_id = document.id

    tache_1 = ai_queue.planifier_fiche_revision_document(document_id)
    tache_2 = ai_queue.planifier_fiche_revision_document(document_id)

    assert tache_1 is not None
    assert tache_2 == tache_1
    with Session(engine) as session:
        assert session.exec(select(func.count()).select_from(FicheRevisionDocument)).one() == 1
        taches = session.exec(
            select(TacheIA).where(
                TacheIA.type_tache == ai_queue.TYPE_FICHE_REVISION_DOCUMENT
            )
        ).all()
        assert len(taches) == 1
        assert taches[0].fiche_revision_document_id is not None
        assert taches[0].statut == StatutTacheIA.EN_ATTENTE
        fiche = session.get(FicheRevisionDocument, taches[0].fiche_revision_document_id)
        assert fiche is not None
        assert fiche.statut == StatutFicheRevisionDocument.EN_ATTENTE


def test_repare_une_fiche_en_attente_sans_tache(monkeypatch):
    engine = moteur_sqlite()
    notifications = []
    monkeypatch.setattr(ai_queue, "engine", engine)
    monkeypatch.setattr(ai_queue, "notifier_tache", lambda task_id: notifications.append(task_id) or True)

    with Session(engine) as session:
        document, _ = creer_document(session)
        fiche = FicheRevisionDocument(
            document_id=document.id,
            statut=StatutFicheRevisionDocument.EN_ATTENTE,
        )
        session.add(fiche)
        session.commit()
        document_id = document.id
        fiche_id = fiche.id

    reparations = ai_queue.reparer_fiches_revision_documents_bloquees(
        document_ids=[document_id],
        max_documents=5,
    )

    assert reparations == 1
    with Session(engine) as session:
        fiche = session.get(FicheRevisionDocument, fiche_id)
        taches = session.exec(
            select(TacheIA).where(
                TacheIA.type_tache == ai_queue.TYPE_FICHE_REVISION_DOCUMENT,
                TacheIA.fiche_revision_document_id == fiche_id,
            )
        ).all()
        assert fiche.statut == StatutFicheRevisionDocument.EN_ATTENTE
        assert len(taches) == 1
        assert taches[0].statut == StatutTacheIA.EN_ATTENTE
        assert taches[0].id in notifications


def test_repare_une_fiche_en_attente_dont_la_tache_est_terminale(monkeypatch):
    engine = moteur_sqlite()
    monkeypatch.setattr(ai_queue, "engine", engine)
    monkeypatch.setattr(ai_queue, "notifier_tache", lambda _task_id: True)

    with Session(engine) as session:
        document, _ = creer_document(session)
        document_id = document.id

    task_id = ai_queue.planifier_fiche_revision_document(document_id)
    assert task_id is not None
    with Session(engine) as session:
        task = session.get(TacheIA, task_id)
        fiche = session.exec(
            select(FicheRevisionDocument).where(
                FicheRevisionDocument.document_id == document_id
            )
        ).first()
        task.statut = StatutTacheIA.TERMINEE
        fiche.statut = StatutFicheRevisionDocument.EN_ATTENTE
        session.add(task)
        session.add(fiche)
        session.commit()
        fiche_id = fiche.id

    reparations = ai_queue.reparer_fiches_revision_documents_bloquees(
        document_ids=[document_id],
    )

    assert reparations == 1
    with Session(engine) as session:
        task = session.get(TacheIA, task_id)
        fiche = session.get(FicheRevisionDocument, fiche_id)
        assert task.statut == StatutTacheIA.EN_ATTENTE
        assert task.nombre_essais == 0
        assert fiche.statut == StatutFicheRevisionDocument.EN_ATTENTE


def test_repare_une_fiche_marquee_terminee_mais_sans_contenu(monkeypatch):
    engine = moteur_sqlite()
    monkeypatch.setattr(ai_queue, "engine", engine)
    monkeypatch.setattr(ai_queue, "notifier_tache", lambda _task_id: True)

    with Session(engine) as session:
        document, _ = creer_document(session)
        fiche = FicheRevisionDocument(
            document_id=document.id,
            statut=StatutFicheRevisionDocument.TERMINEE,
            contenu_json="{}",
        )
        session.add(fiche)
        session.commit()
        fiche_id = fiche.id
        document_id = document.id

    assert ai_queue.reparer_fiches_revision_documents_bloquees(
        document_ids=[document_id],
    ) == 1

    with Session(engine) as session:
        fiche = session.get(FicheRevisionDocument, fiche_id)
        task = session.exec(
            select(TacheIA).where(
                TacheIA.type_tache == ai_queue.TYPE_FICHE_REVISION_DOCUMENT,
                TacheIA.fiche_revision_document_id == fiche_id,
            )
        ).first()
        assert task is not None
        assert task.statut == StatutTacheIA.EN_ATTENTE
        assert fiche.statut == StatutFicheRevisionDocument.EN_ATTENTE


def test_ne_replanifie_pas_une_tache_en_attente_ou_une_fiche_en_echec(monkeypatch):
    engine = moteur_sqlite()
    notifications = []
    monkeypatch.setattr(ai_queue, "engine", engine)
    monkeypatch.setattr(ai_queue, "notifier_tache", lambda task_id: notifications.append(task_id) or True)

    with Session(engine) as session:
        document, _ = creer_document(session)
        document_id = document.id

    task_id = ai_queue.planifier_fiche_revision_document(document_id)
    assert task_id is not None
    notification_count = len(notifications)
    assert ai_queue.reparer_fiches_revision_documents_bloquees(
        document_ids=[document_id],
    ) == 0
    assert len(notifications) == notification_count

    with Session(engine) as session:
        task = session.get(TacheIA, task_id)
        fiche = session.exec(
            select(FicheRevisionDocument).where(
                FicheRevisionDocument.document_id == document_id
            )
        ).first()
        task.statut = StatutTacheIA.ECHOUEE
        fiche.statut = StatutFicheRevisionDocument.ECHOUEE
        session.add(task)
        session.add(fiche)
        session.commit()

    assert ai_queue.reparer_fiches_revision_documents_bloquees(
        document_ids=[document_id],
    ) == 0
    with Session(engine) as session:
        assert session.get(TacheIA, task_id).statut == StatutTacheIA.ECHOUEE


@pytest.mark.parametrize(
    ("statut", "type_document"),
    [
        (StatutDocument.EN_ATTENTE, TypeDocument.COURS),
        (StatutDocument.REJETE, TypeDocument.COURS),
        (StatutDocument.APPROUVE, TypeDocument.ANNALE),
        (StatutDocument.APPROUVE, TypeDocument.CORRIGE),
    ],
)
def test_ne_genere_pas_de_fiche_pour_une_ressource_non_eligible(
    monkeypatch, statut, type_document
):
    engine = moteur_sqlite()
    monkeypatch.setattr(ai_queue, "engine", engine)
    monkeypatch.setattr(ai_queue, "notifier_tache", lambda _task_id: True)
    with Session(engine) as session:
        document, _ = creer_document(
            session,
            statut=statut,
            type_document=type_document,
        )
        document_id = document.id

    assert ai_queue.planifier_fiche_revision_document(document_id) is None
    with Session(engine) as session:
        assert session.exec(select(func.count()).select_from(FicheRevisionDocument)).one() == 0
        assert session.exec(
            select(func.count())
            .select_from(TacheIA)
            .where(TacheIA.type_tache == ai_queue.TYPE_FICHE_REVISION_DOCUMENT)
        ).one() == 0


def test_fiche_est_generee_depuis_le_texte_reel_et_enregistree(monkeypatch):
    engine = moteur_sqlite()
    monkeypatch.setattr(course_revision, "engine", engine)

    texte_cours = (
        "Algèbre linéaire. Une matrice est un tableau rectangulaire de coefficients. "
        "Pour une matrice carrée d'ordre deux A=[[a,b],[c,d]], le déterminant est ad-bc. "
        "Le produit AB est défini si le nombre de colonnes de A égale le nombre de lignes de B. "
    ) * 8

    @contextmanager
    def faux_fichier(_reference):
        yield Path("/tmp/cours-source.pdf")

    contexte_capture = {}
    def generer(contexte, mode_document=False):
        contexte_capture["contexte"] = contexte
        contexte_capture["mode_document"] = mode_document
        return course_revision.normaliser_fiche_revision(fixture_fiche())

    monkeypatch.setattr(course_revision, "ouvrir_fichier_local", faux_fichier)
    monkeypatch.setattr(course_revision, "extraire_texte", lambda _chemin: texte_cours)
    monkeypatch.setattr(course_revision, "_generer_contenu_ia", generer)

    with Session(engine) as session:
        document, utilisateur = creer_document(session)
        fiche = FicheRevisionDocument(
            document_id=document.id,
            statut=StatutFicheRevisionDocument.EN_ATTENTE,
        )
        session.add(fiche)
        session.commit()
        session.refresh(fiche)
        fiche_id = fiche.id
        document_id = document.id
        uploader_id = utilisateur.id

    course_revision.generer_et_sauvegarder_fiche_revision_document(fiche_id)

    with Session(engine) as session:
        fiche = session.get(FicheRevisionDocument, fiche_id)
        assert fiche is not None
        assert fiche.statut == StatutFicheRevisionDocument.TERMINEE
        contenu = json.loads(fiche.contenu_json)
        sources = json.loads(fiche.sources_json)
        assert "matrices" in contenu["resume"].lower()
        assert sources["document_id"] == document_id
        assert sources["caracteres_extraits"] == len(texte_cours.strip())
        notifications = session.exec(
            select(Notification).where(
                Notification.destinataire_id == uploader_id,
                Notification.type_notification == TypeNotification.FICHE_REVISION_DOCUMENT_PRETE,
            )
        ).all()
        assert len(notifications) == 1

    contexte = contexte_capture["contexte"]
    assert contexte_capture["mode_document"] is True
    assert "déterminant" in contexte["source_document"]["contenu_extrait"].lower()
    assert contexte["source_document"]["reference"] == "TEST-COURS-AUTO-0001"


def test_refuse_une_extraction_illisible_plutot_que_d_inventer(monkeypatch):
    engine = moteur_sqlite()
    monkeypatch.setattr(course_revision, "engine", engine)

    @contextmanager
    def faux_fichier(_reference):
        yield Path("/tmp/cours-vide.pdf")

    monkeypatch.setattr(course_revision, "ouvrir_fichier_local", faux_fichier)
    monkeypatch.setattr(course_revision, "extraire_texte", lambda _chemin: "Sciences et cours.")

    with Session(engine) as session:
        document, _ = creer_document(session)
        fiche = FicheRevisionDocument(
            document_id=document.id,
            statut=StatutFicheRevisionDocument.EN_ATTENTE,
        )
        session.add(fiche)
        session.commit()
        session.refresh(fiche)
        fiche_id = fiche.id

    with pytest.raises(RuntimeError, match="insuffisant"):
        course_revision.generer_et_sauvegarder_fiche_revision_document(fiche_id)


def test_hub_et_fiche_document_sont_des_templates_compilables():
    dossier = Path(__file__).resolve().parents[1] / "app" / "templates"
    environnement = Environment(loader=FileSystemLoader(str(dossier)))
    hub = environnement.get_template("document_parcours.html")
    fiche = environnement.get_template("document_revision.html")
    bibliotheque = environnement.get_template("documents_list.html")
    source_hub = (dossier / "document_parcours.html").read_text(encoding="utf-8")
    source_fiche = (dossier / "document_revision.html").read_text(encoding="utf-8")

    assert hub.name == "document_parcours.html"
    assert fiche.name == "document_revision.html"
    assert 'document.type_document.value == "cours"' in source_hub
    assert "/documents/{{ document.id }}/revision/telecharger/pdf" in source_hub
    assert "/documents/{{ document.id }}/revision/telecharger/docx" in source_hub
    assert "source_document" not in source_fiche
    assert "data-rendu" in source_fiche
    assert "Exercices conseillés pour toi" in source_fiche
    assert "preuves_a_obtenir" in source_fiche
    assert "Télécharger la fiche PDF" in source_fiche
    assert "Télécharger la version Word" in source_fiche

    # La bibliothèque doit exposer directement la consultation et les téléchargements,
    # pas seulement les laisser cachés dans le parcours du document.
    source_bibliotheque = (dossier / "documents_list.html").read_text(encoding="utf-8")
    source_route = (
        Path(__file__).resolve().parents[1] / "app" / "routers" / "documents_router.py"
    ).read_text(encoding="utf-8")
    assert bibliotheque.name == "documents_list.html"
    assert "fiches_revision_documents" in source_route
    assert "Consulter la fiche de révision" in source_bibliotheque
    assert "/documents/{{ doc.id }}/revision/telecharger/pdf" in source_bibliotheque
    assert "/documents/{{ doc.id }}/revision/telecharger/docx" in source_bibliotheque
    assert 'doc.type_document.value == "cours"' in source_bibliotheque
    assert "doc-revision-telechargements" in source_bibliotheque
    assert "doc-revision-statut-attente" in source_bibliotheque
    assert "En attente" in source_bibliotheque
    assert "À planifier" in source_bibliotheque
    assert "La fiche est inscrite dans la file de traitement IA" in source_bibliotheque
    assert "Préparer ma fiche" in source_bibliotheque
    assert "reparer_fiches_revision_documents_bloquees" in source_route
    assert "Fiche incomplète" in source_bibliotheque
    assert "Échec à relancer" in source_bibliotheque
    assert "Le statut est terminé, mais le carnet ne contient pas de fiche exploitable." in source_hub



def test_fiche_document_personnalisee_par_etudiant_sans_fuite_ni_mutation():
    from datetime import timedelta

    engine = moteur_sqlite()
    with Session(engine) as session:
        document, etudiant_a = creer_document(session)
        etudiant_b = Utilisateur(
            nom="Étudiant B",
            telephone="+261340099992",
            mot_de_passe_hash="test-hash-b",
            role=RoleUtilisateur.ETUDIANT,
        )
        session.add(etudiant_b)
        session.commit()
        session.refresh(etudiant_b)

        progression_a = ProgressionNotion(
            utilisateur_id=etudiant_a.id,
            matiere="Mathématiques",
            niveau="L1",
            notion="Déterminant",
            nb_questions=8,
            nb_reussites=2,
            nb_erreurs=6,
            score_maitrise=25,
            confiance_maitrise=30,
            maitrise_confirmee=False,
            prochaine_revision_le=datetime.utcnow(),
        )
        progression_b = ProgressionNotion(
            utilisateur_id=etudiant_b.id,
            matiere="Mathématiques",
            niveau="L1",
            notion="Produit matriciel",
            nb_questions=10,
            nb_reussites=9,
            nb_erreurs=1,
            score_maitrise=88,
            confiance_maitrise=90,
            maitrise_confirmee=True,
            prochaine_revision_le=datetime.utcnow() + timedelta(days=5),
        )
        session.add_all([progression_a, progression_b])
        session.commit()

        fiche_source = fixture_fiche()
        fiche_source_originale = json.dumps(fiche_source, ensure_ascii=False, sort_keys=True)
        fiche_a = course_revision.personnaliser_fiche_revision_document(
            session, document, etudiant_a.id, fiche_source
        )
        fiche_b = course_revision.personnaliser_fiche_revision_document(
            session, document, etudiant_b.id, fiche_source
        )

        profil_a = fiche_a["profil_personnalise"]
        profil_b = fiche_b["profil_personnalise"]

        assert json.dumps(fiche_source, ensure_ascii=False, sort_keys=True) == fiche_source_originale
        assert profil_a["priorites"][0]["notion"] == "Déterminant"
        assert profil_b["priorites"][0]["notion"] == "Produit matriciel"
        assert "Produit matriciel" not in [p["notion"] for p in profil_a["priorites"]]
        assert "Déterminant" not in [p["notion"] for p in profil_b["priorites"]]
        assert fiche_a["exercices"][0]["notion"] == "Déterminant"
        assert fiche_b["exercices"][0]["notion"] == "Produit matriciel"
        assert profil_a["exercices_recommandes"][0]["notion"] == "Déterminant"
        assert profil_b["exercices_recommandes"][0]["notion"] == "Produit matriciel"
        assert any(item["moment"] == "Dans 7 jours" for item in fiche_a["plan_revision"])
        assert any(item["moment"].startswith("Le ") for item in fiche_b["plan_revision"])
        assert "Déterminant" not in profil_b["prochaine_action"]
        assert "Produit matriciel" not in profil_a["prochaine_action"]


def test_fiche_document_personnalisee_exports_priorites_et_exercices():
    fiche = fixture_fiche()
    fiche["profil_personnalise"] = {
        "titre": "Ta fiche personnalisée",
        "mode": "Adaptée à ton parcours",
        "message": "Une notion est prioritaire pour toi.",
        "priorites": [{
            "notion": "Déterminant",
            "statut": "À retravailler en premier",
            "raison": "Les dernières réponses sont fragiles.",
            "action": "Revois ad-bc avant un nouvel essai.",
            "revision_prevue": "À revoir aujourd'hui",
        }],
        "exercices_recommandes": [{
            "notion": "Déterminant",
            "difficulte": "Facile",
            "enonce": r"Calcule \(det(A)=ad-bc\).",
            "indice": "Calcule ad puis bc.",
            "raison": "Exercice ciblé selon ton historique.",
        }],
        "preuves_a_obtenir": ["Résoudre une question nouvelle."],
        "points_forts": [],
        "tendance_quiz": "Quiz à reprendre en priorité.",
        "conseil_tuteur": "Explique les étapes avec tes mots.",
        "prochaine_action": "Commence par le déterminant.",
    }
    cours = type("CoursExport", (), {"nom": "Algèbre", "matiere": "Mathématiques", "niveau": "L1"})()
    seance = type("SeanceExport", (), {"titre": "Matrices", "date_fin_reelle": datetime.utcnow(), "date_creation": datetime.utcnow()})()
    pdf = course_revision.generer_pdf(fiche, cours, seance, "Étudiant A")
    docx = course_revision.generer_docx(fiche, cours, seance, "Étudiant A")
    assert pdf.startswith(b"%PDF")
    assert docx.startswith(b"PK")
