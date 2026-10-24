"""Non-regression tests for the secondary-school referential and circle targeting."""
from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

from app.models import (
    CercleEtude,
    Document,
    NiveauScolaire,
    OptionScolaire,
    ReferentielScolaire,
    RoleUtilisateur,
    StatutCercle,
    StatutDocument,
    TypeDocument,
    Utilisateur,
)
from app.referentiel_academique import (
    condition_cercles_disponibles,
    profil_correspond_au_cercle,
    type_cercle,
)


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _activer_cles_etrangeres(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def _school_catalogue(session: Session):
    referentiel = ReferentielScolaire(
        code="MEN-test-2026",
        libelle="Référentiel de test",
        source_officielle="https://www.education.gov.mg/repartition-annuelle-du-programme-scolaire/",
        statut="partiel",
    )
    session.add(referentiel)
    session.commit()
    session.refresh(referentiel)

    niveau = NiveauScolaire(
        referentiel_id=referentiel.id,
        code="TERM",
        libelle="Terminale",
        cycle="lycee",
        ordre=7,
        est_actif=True,
        source_officielle=referentiel.source_officielle,
        statut_validation="verifie",
    )
    session.add(niveau)
    session.commit()
    session.refresh(niveau)

    option = OptionScolaire(
        referentiel_id=referentiel.id,
        niveau_id=niveau.id,
        code="D",
        libelle="Série D",
        type_option="serie",
        est_active=True,
        source_officielle=referentiel.source_officielle,
        statut_validation="verifie",
    )
    session.add(option)
    session.commit()
    session.refresh(option)
    return referentiel, niveau, option


def _user(session: Session, *, niveau_id: int, option_id: int | None, cycle="lycee", profile="eleve"):
    user = Utilisateur(
        nom="Élève de test",
        telephone="0340000001",
        mot_de_passe_hash="hash",
        role=RoleUtilisateur.ETUDIANT,
        profil_souhaite=profile,
        cycle_education=cycle,
        niveau_scolaire_id=niveau_id,
        option_scolaire_id=option_id,
        statut_verification_enseignant="en_attente" if profile == "professeur" else "non_concerne",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_cercle_scolaire_correspond_au_niveau_et_a_la_serie():
    engine, session = _session()
    _, niveau, option = _school_catalogue(session)
    user = _user(session, niveau_id=niveau.id, option_id=option.id)
    cercle = CercleEtude(
        nom="Révisions Terminale D",
        createur_id=user.id,
        statut=StatutCercle.ACTIF,
        portee_academique="scolaire",
        niveau_scolaire_id=niveau.id,
        option_scolaire_id=option.id,
    )
    session.add(cercle)
    session.commit()
    session.refresh(cercle)

    assert type_cercle(cercle, session) == "scolaire"
    assert profil_correspond_au_cercle(user, cercle, session) is True
    assert session.exec(
        select(CercleEtude).where(condition_cercles_disponibles(user, session))
    ).all() == [cercle]

    sans_serie = _user(session, niveau_id=niveau.id, option_id=None)
    assert profil_correspond_au_cercle(sans_serie, cercle, session) is False
    session.close()
    engine.dispose()


def test_demande_professeur_ne_donne_pas_le_role_effectif_professeur():
    engine, session = _session()
    _, niveau, option = _school_catalogue(session)
    teacher_request = _user(
        session,
        niveau_id=niveau.id,
        option_id=option.id,
        profile="professeur",
    )

    assert teacher_request.profil_souhaite == "professeur"
    assert teacher_request.statut_verification_enseignant == "en_attente"
    assert teacher_request.role == RoleUtilisateur.ETUDIANT
    session.close()
    engine.dispose()


def test_document_scolaire_est_valide_sans_filiere_universitaire():
    engine, session = _session()
    _, niveau, option = _school_catalogue(session)
    user = _user(session, niveau_id=niveau.id, option_id=option.id)
    document = Document(
        reference="TEST-SCOLAIRE-2026-001",
        titre="Cours de mathématiques",
        matiere="Mathématiques",
        type_document=TypeDocument.COURS,
        annee=2026,
        filiere_id=None,
        portee_academique="scolaire",
        niveau_scolaire_id=niveau.id,
        option_scolaire_id=option.id,
        uploader_id=user.id,
        chemin_fichier="scolaire/test.pdf",
        statut=StatutDocument.EN_ATTENTE,
    )
    session.add(document)
    session.commit()
    session.refresh(document)

    assert document.id is not None
    assert document.filiere_id is None
    assert document.niveau_scolaire_id == niveau.id
    session.close()
    engine.dispose()
