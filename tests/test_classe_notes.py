from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine, select
from sqlalchemy.pool import StaticPool

from app.models import Cours, NoteSeance, RoleUtilisateur, Seance, Utilisateur


ROOT = Path(__file__).resolve().parents[1]


def utilisateur(nom, telephone, role):
    return Utilisateur(nom=nom, telephone=telephone, mot_de_passe_hash="hash-test", role=role)


def test_notes_personnelles_isolees_par_etudiant():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        prof = utilisateur("Professeur", "+261340000801", RoleUtilisateur.PROFESSEUR)
        eleve_a = utilisateur("Élève A", "+261340000802", RoleUtilisateur.ETUDIANT)
        eleve_b = utilisateur("Élève B", "+261340000803", RoleUtilisateur.ETUDIANT)
        session.add_all([prof, eleve_a, eleve_b])
        session.commit()
        session.refresh(prof)
        session.refresh(eleve_a)
        session.refresh(eleve_b)
        cours = Cours(nom="Mathématiques", matiere="Mathématiques", niveau="L1", professeur_id=prof.id)
        session.add(cours)
        session.commit()
        session.refresh(cours)
        seance = Seance(cours_id=cours.id, titre="Matrices", nom_salle_livekit="notes-privees-test")
        session.add(seance)
        session.commit()
        session.refresh(seance)
        session.add_all([
            NoteSeance(seance_id=seance.id, cours_id=cours.id, utilisateur_id=eleve_a.id, contenu="Notes privées A"),
            NoteSeance(seance_id=seance.id, cours_id=cours.id, utilisateur_id=eleve_b.id, contenu="Notes privées B"),
        ])
        session.commit()
        note_a = session.exec(select(NoteSeance).where(NoteSeance.seance_id == seance.id, NoteSeance.utilisateur_id == eleve_a.id)).one()
        note_b = session.exec(select(NoteSeance).where(NoteSeance.seance_id == seance.id, NoteSeance.utilisateur_id == eleve_b.id)).one()
        assert note_a.contenu == "Notes privées A"
        assert note_b.contenu == "Notes privées B"
        assert note_a.id != note_b.id


def test_un_etudiant_ne_peut_avoir_qu_une_note_par_seance():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        prof = utilisateur("Professeur", "+261340000811", RoleUtilisateur.PROFESSEUR)
        eleve = utilisateur("Élève", "+261340000812", RoleUtilisateur.ETUDIANT)
        session.add_all([prof, eleve])
        session.commit()
        session.refresh(prof)
        session.refresh(eleve)
        cours = Cours(nom="Physique", matiere="Physique", niveau="L1", professeur_id=prof.id)
        session.add(cours)
        session.commit()
        session.refresh(cours)
        seance = Seance(cours_id=cours.id, titre="Optique", nom_salle_livekit="notes-unique-test")
        session.add(seance)
        session.commit()
        session.refresh(seance)
        session.add(NoteSeance(seance_id=seance.id, cours_id=cours.id, utilisateur_id=eleve.id, contenu="Première note"))
        session.commit()
        session.add(NoteSeance(seance_id=seance.id, cours_id=cours.id, utilisateur_id=eleve.id, contenu="Doublon"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_salle_expose_notes_liens_espace_ecran_et_commandes():
    source = (ROOT / "app" / "templates" / "classe_salle.html").read_text(encoding="utf-8")
    assert 'id="btn-notes"' in source
    assert 'id="notes-saisie"' in source
    assert 'id="btn-notes-ia"' in source
    assert 'href="/cercles"' in source
    assert 'target="_blank" rel="noopener"' in source
    assert "tuile-partage-ecran" in source
    assert "Agrandir" in source and "Réduire" in source
    assert "sendBeacon" in source


def test_routes_notes_filtrent_par_utilisateur_et_verifient_acces():
    source = (ROOT / "app" / "routers" / "classe_router.py").read_text(encoding="utf-8")
    assert "NoteSeance.utilisateur_id == utilisateur.id" in source
    assert "_est_inscrit(session, cours.id, utilisateur.id)" in source
    assert "verifier_csrf" in source
    assert "classe_notes.organiser_notes" in source


def test_notes_restent_accessibles_apres_une_seance_et_ont_une_page_dediee():
    router = (ROOT / "app" / "routers" / "classe_router.py").read_text(encoding="utf-8")
    cours = (ROOT / "app" / "templates" / "classe_detail.html").read_text(encoding="utf-8")
    page = (ROOT / "app" / "templates" / "classe_notes.html").read_text(encoding="utf-8")
    assert '@router.get("/classe/seances/{seance_id}/notes")' in router
    assert 'href="/classe/seances/{{ seance.id }}/notes"' in cours
    assert "mes-notes-seance-" in page
    assert "beforeunload" in page
    assert "Organiser avec l'IA" in page


def test_page_notes_compile_avec_jinja():
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"))
    assert env.get_template("classe_notes.html") is not None
