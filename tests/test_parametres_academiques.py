"""Tests du référentiel pédagogique configurable par établissement."""

from datetime import datetime

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.bulletins import calculer_moyenne_generale, construire_snapshot_bulletin
from app.models import (
    CoefficientMatiereEtablissement,
    Cours,
    Devoir,
    EtablissementScolaire,
    MatiereScolaire,
    NiveauScolaire,
    OptionScolaire,
    ParametresAcademiquesEtablissement,
    ReferentielScolaire,
    RenduDevoir,
    RoleUtilisateur,
    Utilisateur,
)
from app.routers.bulletin_router import _periode_canonique


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


def _utilisateur(nom: str, telephone: str, role: RoleUtilisateur) -> Utilisateur:
    return Utilisateur(
        nom=nom,
        telephone=telephone,
        mot_de_passe_hash="hash-test",
        role=role,
        profil_souhaite="enseignant" if role == RoleUtilisateur.PROFESSEUR else "eleve",
        statut_verification_enseignant=(
            "approuve" if role == RoleUtilisateur.PROFESSEUR else "non_concerne"
        ),
    )


def _construire_cas_scolaire(db: Session):
    professeur = _utilisateur("Enseignant", "03400009001", RoleUtilisateur.PROFESSEUR)
    eleve = _utilisateur("Élève", "03400009002", RoleUtilisateur.ETUDIANT)
    etablissement = EtablissementScolaire(
        nom="Établissement de test",
        code="ETAB-TEST-ACA",
        est_verifie=True,
        est_actif=True,
    )
    db.add_all([professeur, eleve, etablissement])
    db.commit()
    db.refresh(professeur)
    db.refresh(eleve)
    db.refresh(etablissement)

    referentiel = ReferentielScolaire(
        code="TEST-2026",
        libelle="Référentiel scolaire de test",
        annee_scolaire="2026-2027",
        source_officielle="https://education.gov.mg/",
        statut="complet",
    )
    db.add(referentiel)
    db.commit()
    db.refresh(referentiel)

    niveau = NiveauScolaire(
        referentiel_id=referentiel.id,
        code="TERM",
        libelle="Terminale",
        cycle="lycee",
        ordre=7,
        est_actif=True,
        statut_validation="verifie",
    )
    matiere = MatiereScolaire(
        code="MATHEMATIQUES-TEST",
        libelle="Mathématiques",
        est_active=True,
        statut_validation="verifie",
    )
    db.add_all([niveau, matiere])
    db.commit()
    db.refresh(niveau)
    db.refresh(matiere)

    option = OptionScolaire(
        referentiel_id=referentiel.id,
        niveau_id=niveau.id,
        code="S",
        libelle="Série S",
        type_option="serie",
        est_active=True,
        statut_validation="verifie",
    )
    db.add(option)
    db.commit()
    db.refresh(option)

    configuration = ParametresAcademiquesEtablissement(
        etablissement_id=etablissement.id,
        annee_scolaire="2026-2027",
        calendrier="trimestre",
        periodes_json='[{"code":"T1","libelle":"Trimestre 1"},{"code":"T2","libelle":"Trimestre 2"}]',
        note_maximale=100,
        seuil_reussite=50,
        est_actif=True,
    )
    db.add(configuration)
    db.commit()
    db.refresh(configuration)

    cours = Cours(
        nom="Mathématiques — Terminale S",
        matiere="Mathématiques",
        niveau="Terminale",
        portee_academique="scolaire",
        niveau_scolaire_id=niveau.id,
        option_scolaire_id=option.id,
        etablissement_scolaire_id=etablissement.id,
        matiere_scolaire_id=matiere.id,
        professeur_id=professeur.id,
    )
    db.add(cours)
    db.commit()
    db.refresh(cours)

    devoir = Devoir(
        cours_id=cours.id,
        titre="Contrôle de mathématiques",
        bareme=20,
        coefficient=1,
        periode="T1",
    )
    db.add(devoir)
    db.commit()
    db.refresh(devoir)
    db.add(RenduDevoir(
        devoir_id=devoir.id,
        utilisateur_id=eleve.id,
        chemin_fichier="rendus/controle.pdf",
        nom_fichier_original="controle.pdf",
        note=15,
        date_correction=datetime(2026, 10, 12),
    ))
    db.add(CoefficientMatiereEtablissement(
        parametres_id=configuration.id,
        niveau_id=niveau.id,
        option_id=option.id,
        matiere_id=matiere.id,
        coefficient=2.5,
        obligatoire=True,
    ))
    db.commit()
    return cours, eleve, configuration


def test_bulletin_applique_le_bareme_et_le_coefficient_de_la_serie(db):
    cours, eleve, configuration = _construire_cas_scolaire(db)
    snapshot = construire_snapshot_bulletin(
        db, cours, eleve, "T1", "Bon travail.",
        publie_le=datetime(2026, 11, 20, 10, 30),
    )

    assert configuration.note_maximale == 100
    assert snapshot["moyenne"] == 75.0
    assert snapshot["moyenne_sur"] == 100.0
    assert snapshot["seuil_reussite"] == 50.0
    assert snapshot["coefficient_matiere"] == 2.5
    assert snapshot["annee_scolaire"] == "2026-2027"
    assert snapshot["evaluations"][0]["note_sur_20"] == 15.0
    assert snapshot["evaluations"][0]["note_sur_echelle"] == 75.0


def test_un_bulletin_scolaire_n_accepte_que_les_periodes_configurees(db):
    cours, _eleve, _configuration = _construire_cas_scolaire(db)

    assert _periode_canonique(db, cours.id, "T1") == "T1"
    assert _periode_canonique(db, cours.id, "Trimestre 2") is None
    # Il n'y a pas encore de devoir en T2 : la période est connue mais
    # aucun bulletin ne peut être créé sans évaluation associée.
    assert _periode_canonique(db, cours.id, "S2") is None


def test_moyenne_generale_ponderee_les_matieres_sur_20(db):
    snapshots = [
        {
            "version": 1,
            "cours_id": 1,
            "periode": "T1",
            "moyenne": 10,
            "moyenne_sur": 20,
            "coefficient_matiere": 1,
            "evaluations": [],
        },
        {
            "version": 1,
            "cours_id": 2,
            "periode": "T1",
            "moyenne": 100,
            "moyenne_sur": 100,
            "coefficient_matiere": 3,
            "evaluations": [],
        },
    ]

    assert calculer_moyenne_generale(snapshots, "T1") == 17.5


def test_anciens_snapshots_conservent_la_moyenne_a_coefficients_neutres(db):
    anciens = [
        {"version": 1, "cours_id": 1, "periode": "T1", "moyenne": 12, "evaluations": []},
        {"version": 1, "cours_id": 2, "periode": "T1", "moyenne": 16, "evaluations": []},
    ]

    assert calculer_moyenne_generale(anciens, "T1") == 14.0
