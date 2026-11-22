"""Tests du journal d'audit des paramètres académiques."""

import json

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

from app.models import (
    EtablissementScolaire,
    ParametresAcademiquesEvenement,
    RoleUtilisateur,
    Utilisateur,
)
from app.routers.admin_scolaire_router import _journaliser_parametres_academiques


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


def _admin_et_etablissement(session: Session):
    admin = Utilisateur(
        nom="Administrateur audit",
        telephone="03400009991",
        mot_de_passe_hash="hash-test",
        role=RoleUtilisateur.ADMIN,
        profil_souhaite="admin",
        statut_verification_enseignant="non_concerne",
    )
    etablissement = EtablissementScolaire(
        nom="Établissement audit",
        code="ETAB-AUDIT-TEST",
        est_verifie=True,
        est_actif=True,
    )
    session.add_all([admin, etablissement])
    session.commit()
    session.refresh(admin)
    session.refresh(etablissement)
    return admin, etablissement


def test_journal_conserve_acteur_et_valeurs_avant_apres_dans_la_meme_transaction(db):
    admin, etablissement = _admin_et_etablissement(db)

    _journaliser_parametres_academiques(
        db,
        admin=admin,
        etablissement_id=etablissement.id,
        annee_scolaire="2026-2027",
        action="modification",
        entite_type="configuration",
        entite_id=42,
        avant={
            "calendrier": "trimestre",
            "note_maximale": 20.0,
            "seuil_reussite": 10.0,
        },
        apres={
            "calendrier": "semestre",
            "note_maximale": 100.0,
            "seuil_reussite": 50.0,
        },
        contexte={"etablissement": etablissement.nom},
    )
    db.commit()

    evenement = db.exec(
        select(ParametresAcademiquesEvenement).where(
            ParametresAcademiquesEvenement.etablissement_id == etablissement.id
        )
    ).one()
    details = json.loads(evenement.details_json)

    assert evenement.acteur_id == admin.id
    assert evenement.annee_scolaire == "2026-2027"
    assert evenement.action == "modification"
    assert evenement.entite_type == "configuration"
    assert evenement.entite_id == 42
    assert details["avant"]["note_maximale"] == 20.0
    assert details["apres"]["note_maximale"] == 100.0
    assert details["contexte"]["etablissement"] == etablissement.nom
    assert evenement.date_evenement is not None


def test_journal_refuse_une_action_non_autorisee(db):
    admin, etablissement = _admin_et_etablissement(db)
    db.add(
        ParametresAcademiquesEvenement(
            etablissement_id=etablissement.id,
            annee_scolaire="2026-2027",
            acteur_id=admin.id,
            action="effacement_total",
            entite_type="configuration",
            entite_id=42,
            details_json="{}",
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
