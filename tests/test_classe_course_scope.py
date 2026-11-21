from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine

from app.models import (
    CycleEnseigne,
    EtablissementScolaire,
    MatiereScolaire,
    NiveauScolaire,
    OptionScolaire,
    ProgrammeMatiereScolaire,
    ReferentielScolaire,
    RoleUtilisateur,
    Utilisateur,
)
from app.routers.classe_router import (
    _cycles_enseignes_utilisateur,
    _valider_cible_cours_scolaire,
)

ROOT = Path(__file__).resolve().parents[1]


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _activer_cles_etrangeres(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def _catalogue(session):
    referentiel = ReferentielScolaire(
        code="MEN-COURSE-TEST",
        libelle="Référentiel scolaire de test",
        source_officielle="https://www.education.gov.mg/",
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
        est_active=True,
        source_officielle=referentiel.source_officielle,
        statut_validation="verifie",
    )
    session.add(option)
    session.commit()
    session.refresh(option)

    matiere = MatiereScolaire(
        code="MAT-TEST",
        libelle="Mathématiques",
        libelle_malagasy="Matematika",
        est_active=True,
        statut_validation="verifie",
        source_officielle=referentiel.source_officielle,
    )
    session.add(matiere)
    session.commit()
    session.refresh(matiere)

    programme = ProgrammeMatiereScolaire(
        referentiel_id=referentiel.id,
        niveau_id=niveau.id,
        option_id=option.id,
        matiere_id=matiere.id,
        obligatoire=True,
        source_officielle=referentiel.source_officielle,
        statut_validation="verifie",
    )
    session.add(programme)
    session.commit()
    return referentiel, niveau, option, matiere


def _professeur(session, *, cycle="lycee", cycles=()):
    professeur = Utilisateur(
        nom="Professeur de test",
        telephone=telephone,
        mot_de_passe_hash="hash-test",
        role=RoleUtilisateur.PROFESSEUR,
        profil_souhaite="professeur",
        cycle_education=cycle,
        statut_verification_enseignant="approuve",
    )
    session.add(professeur)
    session.commit()
    session.refresh(professeur)
    for valeur in cycles:
        session.add(CycleEnseigne(
            utilisateur_id=professeur.id,
            cycle_education=valeur,
        ))
    if cycles:
        session.commit()
    return professeur


def test_creer_cours_scolaire_reutilise_niveau_option_et_matiere_verifies():
    engine, session = _session()
    try:
        _, niveau, option, matiere = _catalogue(session)
        professeur = _professeur(session, cycle="lycee")

        niveau_ref, option_ref, matiere_ref, etablissement_ref = _valider_cible_cours_scolaire(
            session,
            professeur,
            niveau_id=niveau.id,
            option_id=option.id,
            matiere_id=matiere.id,
            etablissement_id=None,
            cycle_declare="lycee",
        )

        assert niveau_ref.libelle == "Terminale"
        assert option_ref.libelle == "Série D"
        assert matiere_ref.libelle == "Mathématiques"
        assert etablissement_ref is None
    finally:
        session.close()
        engine.dispose()


def test_matiere_scolaire_doit_appartenir_au_programme_verifie_du_niveau():
    engine, session = _session()
    try:
        referentiel, niveau, option, _ = _catalogue(session)
        professeur = _professeur(session, cycle="lycee")
        autre_matiere = MatiereScolaire(
            code="MAT-HORS-PROGRAMME",
            libelle="Matière non rattachée",
            est_active=True,
            statut_validation="verifie",
        )
        session.add(autre_matiere)
        session.commit()
        session.refresh(autre_matiere)

        with pytest.raises(ValueError, match="matiere_hors_programme"):
            _valider_cible_cours_scolaire(
                session,
                professeur,
                niveau_id=niveau.id,
                option_id=option.id,
                matiere_id=autre_matiere.id,
                etablissement_id=None,
                cycle_declare="lycee",
            )
    finally:
        session.close()
        engine.dispose()


def test_professeur_ne_peut_pas_creer_un_cours_dans_un_cycle_non_declare():
    engine, session = _session()
    try:
        _, niveau, option, matiere = _catalogue(session)
        professeur = _professeur(session, cycle="primaire")

        with pytest.raises(ValueError, match="cycle_non_autorise"):
            _valider_cible_cours_scolaire(
                session,
                professeur,
                niveau_id=niveau.id,
                option_id=option.id,
                matiere_id=matiere.id,
                etablissement_id=None,
                cycle_declare="lycee",
            )
    finally:
        session.close()
        engine.dispose()


def test_cycle_du_formulaire_doit_correspondre_au_niveau_selectionne():
    engine, session = _session()
    try:
        _, niveau, option, matiere = _catalogue(session)
        professeur = _professeur(session, cycle="lycee")

        with pytest.raises(ValueError, match="niveau_scolaire_invalide"):
            _valider_cible_cours_scolaire(
                session,
                professeur,
                niveau_id=niveau.id,
                option_id=option.id,
                matiere_id=matiere.id,
                etablissement_id=None,
                cycle_declare="college",
            )
    finally:
        session.close()
        engine.dispose()


def test_referentiel_non_verifie_et_etablissement_non_verifie_sont_refuses():
    engine, session = _session()
    try:
        referentiel, niveau, option, matiere = _catalogue(session)
        professeur = _professeur(session, cycle="lycee")
        niveau.statut_validation = "a_verifier"
        session.add(niveau)
        session.commit()

        with pytest.raises(ValueError, match="niveau_scolaire_invalide"):
            _valider_cible_cours_scolaire(
                session,
                professeur,
                niveau_id=niveau.id,
                option_id=option.id,
                matiere_id=matiere.id,
                etablissement_id=None,
                cycle_declare="lycee",
            )

        niveau.statut_validation = "verifie"
        etablissement = EtablissementScolaire(
            nom="Établissement de test",
            region="Atsinanana",
            commune="Toamasina",
            est_actif=True,
            est_verifie=False,
        )
        session.add_all([niveau, etablissement])
        session.commit()
        session.refresh(etablissement)

        with pytest.raises(ValueError, match="etablissement_scolaire_invalide"):
            _valider_cible_cours_scolaire(
                session,
                professeur,
                niveau_id=niveau.id,
                option_id=option.id,
                matiere_id=matiere.id,
                etablissement_id=etablissement.id,
                cycle_declare="lycee",
            )
    finally:
        session.close()
        engine.dispose()


def test_cycles_enseignes_conservent_les_declarations_et_le_repli_universitaire():
    engine, session = _session()
    try:
        professeur = _professeur(session, cycle="lycee", cycles=("primaire", "college"))
        assert _cycles_enseignes_utilisateur(session, professeur) == [
            "primaire",
            "college",
            "lycee",
        ]

        ancien_professeur = _professeur(
            session,
            cycle=None,
            cycles=(),
            telephone="+261340000778",
        )
        ancien_professeur.cycle_education = None
        assert _cycles_enseignes_utilisateur(session, ancien_professeur) == ["universite"]
    finally:
        session.close()
        engine.dispose()


def test_formulaire_cours_scolaire_et_universitaire_se_compile():
    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"))
    assert env.get_template("classe_liste.html") is not None

    template = (ROOT / "app" / "templates" / "classe_liste.html").read_text(encoding="utf-8")
    script = (ROOT / "app" / "static" / "classe-cours-create.js").read_text(encoding="utf-8")
    route = (ROOT / "app" / "routers" / "classe_router.py").read_text(encoding="utf-8")

    assert 'name="portee_academique"' in template
    assert 'name="niveau_scolaire_id"' in template
    assert 'name="matiere_scolaire_id"' in template
    assert "/api/scolaire/niveaux" in script
    assert "/api/scolaire/niveaux/" in script
    assert "ProgrammeMatiereScolaire.statut_validation == \"verifie\"" in route
    assert "CycleEnseigne.utilisateur_id == utilisateur.id" in route
