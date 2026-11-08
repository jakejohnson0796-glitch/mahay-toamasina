from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.models import (
    AffectationSousSalle,
    ConsentementTranscription,
    Cours,
    GroupeSousSalle,
    ReponseSondageSeance,
    RoleUtilisateur,
    Seance,
    SondageSeance,
    TranscriptionSeance,
    Utilisateur,
)

ROOT = Path(__file__).resolve().parents[1]


def creer_utilisateur(nom, telephone, role):
    return Utilisateur(
        nom=nom,
        telephone=telephone,
        mot_de_passe_hash="hash-test",
        role=role,
    )


def creer_base():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def creer_seance(session):
    professeur = creer_utilisateur("Professeur", "+261340000901", RoleUtilisateur.PROFESSEUR)
    eleve_a = creer_utilisateur("Élève A", "+261340000902", RoleUtilisateur.ETUDIANT)
    eleve_b = creer_utilisateur("Élève B", "+261340000903", RoleUtilisateur.ETUDIANT)
    session.add_all([professeur, eleve_a, eleve_b])
    session.commit()
    session.refresh(professeur)
    session.refresh(eleve_a)
    session.refresh(eleve_b)
    cours = Cours(
        nom="Mathématiques",
        matiere="Mathématiques",
        niveau="L1",
        professeur_id=professeur.id,
    )
    session.add(cours)
    session.commit()
    session.refresh(cours)
    seance = Seance(
        cours_id=cours.id,
        titre="Fonctions",
        nom_salle_livekit="interactions-test",
    )
    session.add(seance)
    session.commit()
    session.refresh(seance)
    return professeur, eleve_a, eleve_b, cours, seance


def test_modeles_interactions_creent_le_schema_sqlite():
    engine = creer_base()
    tables = set(SQLModel.metadata.tables)
    attendues = {
        "sondageseance",
        "reponsesondageseance",
        "groupesoussalle",
        "affectationsoussalle",
        "documentpartageseance",
        "consentementtranscription",
        "transcriptionseance",
    }
    assert attendues.issubset(tables)
    engine.dispose()


def test_un_eleve_ne_peut_pas_repondre_deux_fois_au_meme_sondage():
    engine = creer_base()
    with Session(engine) as session:
        _prof, eleve_a, _eleve_b, cours, seance = creer_seance(session)
        sondage = SondageSeance(
            seance_id=seance.id,
            cours_id=cours.id,
            createur_id=1,
            question="Combien font 2 + 2 ?",
            options_json='["3", "4"]',
            type_sondage="quiz",
            bonne_option=1,
        )
        session.add(sondage)
        session.commit()
        session.refresh(sondage)
        session.add(ReponseSondageSeance(
            sondage_id=sondage.id,
            utilisateur_id=eleve_a.id,
            option_index=1,
        ))
        session.commit()
        session.add(ReponseSondageSeance(
            sondage_id=sondage.id,
            utilisateur_id=eleve_a.id,
            option_index=0,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
    engine.dispose()


def test_un_eleve_ne_peut_appartenir_qu_a_une_sous_salle_par_seance():
    engine = creer_base()
    with Session(engine) as session:
        _prof, eleve_a, _eleve_b, _cours, seance = creer_seance(session)
        groupe_a = GroupeSousSalle(
            seance_id=seance.id,
            nom="Groupe 1",
            nom_salle_livekit="interactions-test-groupe-a",
        )
        groupe_b = GroupeSousSalle(
            seance_id=seance.id,
            nom="Groupe 2",
            nom_salle_livekit="interactions-test-groupe-b",
        )
        session.add_all([groupe_a, groupe_b])
        session.commit()
        session.refresh(groupe_a)
        session.refresh(groupe_b)
        session.add(AffectationSousSalle(
            seance_id=seance.id,
            groupe_id=groupe_a.id,
            utilisateur_id=eleve_a.id,
        ))
        session.commit()
        session.add(AffectationSousSalle(
            seance_id=seance.id,
            groupe_id=groupe_b.id,
            utilisateur_id=eleve_a.id,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
    engine.dispose()


def test_consentement_et_transcription_sont_uniques_par_seance():
    engine = creer_base()
    with Session(engine) as session:
        professeur, _eleve_a, _eleve_b, _cours, seance = creer_seance(session)
        session.add(ConsentementTranscription(
            seance_id=seance.id,
            utilisateur_id=professeur.id,
            consenti=True,
        ))
        session.commit()
        session.add(ConsentementTranscription(
            seance_id=seance.id,
            utilisateur_id=professeur.id,
            consenti=False,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(TranscriptionSeance(
            seance_id=seance.id,
            demarree_par_id=professeur.id,
        ))
        session.commit()
        session.add(TranscriptionSeance(
            seance_id=seance.id,
            demarree_par_id=professeur.id,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
    engine.dispose()


def test_routes_interactions_verifient_les_permissions_et_csrf():
    source = (ROOT / "app" / "routers" / "classe_interactions_router.py").read_text(encoding="utf-8")
    assert "Depends(verifier_csrf)" in source
    assert "_est_inscrit(session, cours.id, utilisateur.id)" in source
    assert "AffectationSousSalle.utilisateur_id == utilisateur.id" in source
    assert "StatutDocument.APPROUVE" in source
    assert "document.matiere.strip().casefold()" in source
    assert "ConsentementTranscription.consenti == True" in source
    assert "lister_participants_salle" in source
    assert "arreter_agent_transcription" in source


def test_entree_dans_la_salle_est_bloquee_sans_consentement_si_transcription_active():
    source = (ROOT / "app" / "routers" / "classe_router.py").read_text(encoding="utf-8")
    assert "transcription_active" in source
    assert "ConsentementTranscription.consenti == True" in source
    assert "/transcription/consentement" in source


def test_transcription_stt_sans_enregistrement_audio():
    source = (ROOT / "agents" / "mahay_transcription.py").read_text(encoding="utf-8")
    assert 'agent_name="mahay-transcription"' in source
    assert "groq.STT(model=" in source
    assert "record=False" in source
    readme = (ROOT / "agents" / "README.md").read_text(encoding="utf-8")
    assert "Aucun audio ni aucune vidéo n'est enregistré" in readme
    assert "LIVEKIT_TRANSCRIPTION_AGENT_NAME" in readme


def test_outils_de_salle_et_post_it_sont_presents():
    salle = (ROOT / "app" / "templates" / "classe_salle.html").read_text(encoding="utf-8")
    assert 'id="btn-sondages"' in salle
    assert 'id="btn-groupes"' in salle
    assert 'id="btn-documents"' in salle
    assert 'id="btn-transcription"' in salle
    assert 'src="/static/classe_interactions.js"' in salle

    tableau = (ROOT / "app" / "templates" / "classe_tableau_fragment.html").read_text(encoding="utf-8")
    assert 'data-outil="note"' in tableau
    assert "d.note" in tableau


def test_templates_groupes_et_consentement_compilent():
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"))
    assert env.get_template("classe_sous_salle.html") is not None
    assert env.get_template("classe_transcription_consentement.html") is not None
