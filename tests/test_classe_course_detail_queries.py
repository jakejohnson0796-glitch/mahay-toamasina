"""Tests des requêtes ciblées utilisées par le détail des cours."""

from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.models import (
    Cours,
    FicheRevisionCours,
    RoleUtilisateur,
    Seance,
    StatutSeance,
    Utilisateur,
)
from app.routers.classe_router import _ids_seances_terminees_sans_fiche


def test_seances_terminees_sans_fiche_sont_filtrees_en_une_requete_sql():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    requetes = []

    def capturer_selects(_connexion, _curseur, instruction, _parametres, _contexte, _executemany):
        if instruction.lstrip().upper().startswith("SELECT"):
            requetes.append(instruction)

    try:
        with Session(engine) as session:
            professeur = Utilisateur(
                nom="Professeur",
                telephone="0341200001",
                mot_de_passe_hash="hash-test",
                role=RoleUtilisateur.PROFESSEUR,
            )
            etudiant = Utilisateur(
                nom="Étudiant",
                telephone="0341200002",
                mot_de_passe_hash="hash-test",
                role=RoleUtilisateur.ETUDIANT,
            )
            autre_etudiant = Utilisateur(
                nom="Autre étudiant",
                telephone="0341200003",
                mot_de_passe_hash="hash-test",
                role=RoleUtilisateur.ETUDIANT,
            )
            session.add_all([professeur, etudiant, autre_etudiant])
            session.flush()

            cours = Cours(
                nom="Mathématiques",
                matiere="Mathématiques",
                niveau="L1",
                professeur_id=professeur.id,
            )
            session.add(cours)
            session.flush()

            seance_avec_fiche = Seance(
                cours_id=cours.id,
                titre="Séance 1",
                nom_salle_livekit="fiche-exists-1",
                statut=StatutSeance.TERMINEE,
            )
            seance_fiche_autre = Seance(
                cours_id=cours.id,
                titre="Séance 2",
                nom_salle_livekit="fiche-exists-2",
                statut=StatutSeance.TERMINEE,
            )
            seance_sans_fiche = Seance(
                cours_id=cours.id,
                titre="Séance 3",
                nom_salle_livekit="fiche-exists-3",
                statut=StatutSeance.TERMINEE,
            )
            seance_planifiee = Seance(
                cours_id=cours.id,
                titre="Séance 4",
                nom_salle_livekit="fiche-exists-4",
                statut=StatutSeance.PLANIFIEE,
            )
            session.add_all([
                seance_avec_fiche,
                seance_fiche_autre,
                seance_sans_fiche,
                seance_planifiee,
            ])
            session.flush()

            session.add_all([
                FicheRevisionCours(
                    cours_id=cours.id,
                    seance_id=seance_avec_fiche.id,
                    utilisateur_id=etudiant.id,
                ),
                FicheRevisionCours(
                    cours_id=cours.id,
                    seance_id=seance_fiche_autre.id,
                    utilisateur_id=autre_etudiant.id,
                ),
            ])
            session.commit()

            event.listen(engine, "before_cursor_execute", capturer_selects)
            try:
                manquantes = _ids_seances_terminees_sans_fiche(
                    session,
                    cours.id,
                    etudiant.id,
                )
            finally:
                event.remove(engine, "before_cursor_execute", capturer_selects)

            assert manquantes == [seance_fiche_autre.id, seance_sans_fiche.id]
            assert len(requetes) == 1
            assert "not exists" in requetes[0].casefold()
    finally:
        engine.dispose()
