"""Non-regression tests for the secondary-school referential and circle targeting."""
from sqlalchemy import event
import pytest
from sqlalchemy.exc import IntegrityError
from types import SimpleNamespace
from sqlmodel import SQLModel, Session, create_engine, select

from app.models import (
    CercleEtude,
    CycleEnseigne,
    Document,
    MatiereScolaire,
    NiveauScolaire,
    OptionScolaire,
    ProgrammeMatiereScolaire,
    ReferentielScolaire,
    RoleUtilisateur,
    StatutCercle,
    StatutDocument,
    StatutDemandeCreationCercle,
    DemandeCreationCercle,
    TypeDocument,
    Utilisateur,
)
from app import quiz as quiz_module
from app.routers import admin_scolaire_router, cercles_router, quiz_router, scolaire_router, tuteur_router
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


def _user(session: Session, *, niveau_id: int, option_id: int | None, cycle="lycee", profile="eleve", telephone="0340000001"):
    user = Utilisateur(
        nom="Élève de test",
        telephone=telephone,
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

    sans_serie = _user(session, niveau_id=niveau.id, option_id=None, telephone="0340000002")
    assert profil_correspond_au_cercle(sans_serie, cercle, session) is False
    session.close()
    engine.dispose()


def test_cibles_scolaires_actives_identiques_restent_uniques_avec_champs_optionnels_nuls():
    engine, session = _session()
    _, niveau, serie = _school_catalogue(session)
    user = _user(session, niveau_id=niveau.id, option_id=serie.id)
    original = CercleEtude(
        nom="Cercle cible unique",
        createur_id=user.id,
        statut=StatutCercle.ACTIF,
        portee_academique="scolaire",
        niveau_scolaire_id=niveau.id,
        option_scolaire_id=serie.id,
        etablissement_scolaire_id=None,
        matiere_scolaire_id=None,
    )
    session.add(original)
    session.commit()

    doublon = CercleEtude(
        nom="Doublon cible",
        createur_id=user.id,
        statut=StatutCercle.ACTIF,
        portee_academique="scolaire",
        niveau_scolaire_id=niveau.id,
        option_scolaire_id=serie.id,
        etablissement_scolaire_id=None,
        matiere_scolaire_id=None,
    )
    session.add(doublon)
    try:
        session.commit()
        raise AssertionError("Les index uniques doivent bloquer un cercle cible scolaire en double.")
    except IntegrityError:
        session.rollback()

    cercles = session.exec(
        select(CercleEtude).where(
            CercleEtude.portee_academique == "scolaire",
            CercleEtude.niveau_scolaire_id == niveau.id,
            CercleEtude.option_scolaire_id == serie.id,
        )
    ).all()
    assert len(cercles) == 1
    session.close()
    engine.dispose()


def test_matiere_de_cercle_est_limitee_au_programme_verifie_de_la_classe_et_serie():
    engine, session = _session()
    referentiel, niveau, serie = _school_catalogue(session)
    matiere_validee = MatiereScolaire(
        code="MATIERE_VERIFIEE",
        libelle="Mathématiques",
        source_officielle="https://www.education.gov.mg/repartition-annuelle-du-programme-scolaire/",
        statut_validation="verifie",
        est_active=True,
    )
    matiere_en_attente = MatiereScolaire(
        code="MATIERE_EN_ATTENTE",
        libelle="Philosophie",
        source_officielle="https://www.education.gov.mg/repartition-annuelle-du-programme-scolaire/",
        statut_validation="a_verifier",
        est_active=False,
    )
    session.add_all([matiere_validee, matiere_en_attente])
    session.commit()
    session.refresh(matiere_validee)
    session.refresh(matiere_en_attente)
    session.add_all([
        ProgrammeMatiereScolaire(
            referentiel_id=referentiel.id,
            niveau_id=niveau.id,
            option_id=serie.id,
            matiere_id=matiere_validee.id,
            obligatoire=True,
            source_officielle=matiere_validee.source_officielle,
            statut_validation="verifie",
        ),
        ProgrammeMatiereScolaire(
            referentiel_id=referentiel.id,
            niveau_id=niveau.id,
            option_id=serie.id,
            matiere_id=matiere_en_attente.id,
            obligatoire=True,
            source_officielle=matiere_en_attente.source_officielle,
            statut_validation="a_verifier",
        ),
    ])
    session.commit()

    assert cercles_router._matiere_scolaire_verifiee_pour_cible(
        session,
        referentiel_id=referentiel.id,
        niveau_id=niveau.id,
        matiere_id=matiere_validee.id,
        option_scolaire=serie,
    ) == matiere_validee
    assert cercles_router._matiere_scolaire_verifiee_pour_cible(
        session,
        referentiel_id=referentiel.id,
        niveau_id=niveau.id,
        matiere_id=matiere_en_attente.id,
        option_scolaire=serie,
    ) is None
    # Un mapping validé pour une autre classe ne doit jamais être réutilisé.
    autre_niveau = NiveauScolaire(
        referentiel_id=referentiel.id,
        code="1ERE_TEST",
        libelle="Première",
        cycle="lycee",
        ordre=6,
        est_actif=True,
        source_officielle=referentiel.source_officielle,
        statut_validation="verifie",
    )
    session.add(autre_niveau)
    session.commit()
    session.refresh(autre_niveau)
    assert cercles_router._matiere_scolaire_verifiee_pour_cible(
        session,
        referentiel_id=referentiel.id,
        niveau_id=autre_niveau.id,
        matiere_id=matiere_validee.id,
        option_scolaire=None,
    ) is None

    session.close()
    engine.dispose()


def test_cercles_et_demandes_scolaires_peuvent_cibler_des_matieres_distinctes():
    engine, session = _session()
    referentiel, niveau, serie = _school_catalogue(session)
    user = _user(session, niveau_id=niveau.id, option_id=serie.id)
    matieres = [
        MatiereScolaire(code="MATIERE_A", libelle="Mathématiques", statut_validation="verifie", est_active=True),
        MatiereScolaire(code="MATIERE_B", libelle="Philosophie", statut_validation="verifie", est_active=True),
    ]
    session.add_all(matieres)
    session.commit()
    for item in matieres:
        session.refresh(item)

    for item in matieres:
        session.add(CercleEtude(
            nom=f"Révisions {item.code}",
            createur_id=user.id,
            statut=StatutCercle.ACTIF,
            portee_academique="scolaire",
            niveau_scolaire_id=niveau.id,
            option_scolaire_id=serie.id,
            matiere_scolaire_id=item.id,
        ))
        session.add(DemandeCreationCercle(
            utilisateur_id=user.id,
            portee_academique="scolaire",
            niveau_scolaire_id=niveau.id,
            option_scolaire_id=serie.id,
            matiere_scolaire_id=item.id,
            nom=f"Demande {item.code}",
            raison="Besoin de réviser cette matière.",
        ))
    session.commit()

    circles = session.exec(
        select(CercleEtude).where(
            CercleEtude.portee_academique == "scolaire",
            CercleEtude.niveau_scolaire_id == niveau.id,
            CercleEtude.option_scolaire_id == serie.id,
        )
    ).all()
    requests = session.exec(
        select(DemandeCreationCercle).where(
            DemandeCreationCercle.portee_academique == "scolaire",
            DemandeCreationCercle.niveau_scolaire_id == niveau.id,
            DemandeCreationCercle.option_scolaire_id == serie.id,
        )
    ).all()
    assert {circle.matiere_scolaire_id for circle in circles} == {item.id for item in matieres}
    assert {request.matiere_scolaire_id for request in requests} == {item.id for item in matieres}

    session.close()
    engine.dispose()


def test_option_de_bac_est_rattachee_a_sa_serie_parente_pour_les_cercles():
    engine, session = _session()
    _, niveau, serie = _school_catalogue(session)
    option = OptionScolaire(
        referentiel_id=serie.referentiel_id,
        niveau_id=niveau.id,
        parent_option_id=serie.id,
        code="OPT_D",
        libelle="Option D",
        type_option="option",
        est_active=True,
        statut_validation="verifie",
    )
    session.add(option)
    session.commit()
    session.refresh(option)
    matiere = MatiereScolaire(
        code="PHILOSOPHIE_TEST",
        libelle="Philosophie",
        source_officielle="https://www.education.gov.mg/repartition-annuelle-du-programme-scolaire/",
        statut_validation="verifie",
        est_active=True,
    )
    session.add(matiere)
    session.commit()
    session.refresh(matiere)
    session.add(ProgrammeMatiereScolaire(
        referentiel_id=serie.referentiel_id,
        niveau_id=niveau.id,
        option_id=serie.id,
        matiere_id=matiere.id,
        obligatoire=True,
        source_officielle=matiere.source_officielle,
        statut_validation="verifie",
    ))
    session.commit()

    user = _user(session, niveau_id=niveau.id, option_id=option.id)
    cercle = CercleEtude(
        nom="Révisions de la série",
        createur_id=user.id,
        statut=StatutCercle.ACTIF,
        portee_academique="scolaire",
        niveau_scolaire_id=niveau.id,
        option_scolaire_id=serie.id,
    )
    session.add(cercle)
    session.commit()
    session.refresh(cercle)

    assert profil_correspond_au_cercle(user, cercle, session) is True
    assert session.exec(
        select(CercleEtude).where(condition_cercles_disponibles(user, session))
    ).all() == [cercle]

    payload = scolaire_router.lister_options_scolaires(niveau.id, session=session)
    option_payload = next(item for item in payload if item["id"] == option.id)
    assert option_payload["parent_option_id"] == serie.id
    assert option_payload["libelle_affiche"] == "Série D → Option D"

    matieres = scolaire_router.lister_matieres_scolaires(
        niveau.id, option_id=option.id, session=session
    )
    assert any(item["code"] == "PHILOSOPHIE_TEST" for item in matieres)

    contexte_quiz = quiz_router._contexte_scolaire_quiz(user, session)
    assert quiz_router._matieres_scolaires_disponibles(session, contexte_quiz) == ["Philosophie"]

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


def test_quiz_cible_reconnait_la_classe_scolaire_sans_basculer_en_l1():
    engine, session = _session()
    referentiel, niveau, serie = _school_catalogue(session)
    user = _user(session, niveau_id=niveau.id, option_id=serie.id)

    contexte = quiz_router._contexte_scolaire_quiz(user, session)

    assert contexte == {
        "niveau": "Terminale",
        "cycle_education": "lycee",
        "referentiel_id": referentiel.id,
        "niveau_scolaire_id": niveau.id,
        "option_scolaire_id": serie.id,
        "etablissement_scolaire_id": None,
    }
    assert quiz_module.valider_parametres(
        "Mathématiques", contexte["niveau"], "Moyen", 5
    ) == "Mathématiques"

    session.close()
    engine.dispose()


def test_professeur_sans_classe_peut_garder_un_parcours_scolaire_general():
    engine, session = _session()
    teacher = Utilisateur(
        nom="Demande de professeur sans classe",
        telephone="0340000100",
        mot_de_passe_hash="hash",
        role=RoleUtilisateur.ETUDIANT,
        profil_souhaite="professeur",
        cycle_education="lycee",
        niveau_scolaire_id=None,
        statut_verification_enseignant="en_attente",
    )
    session.add(teacher)
    session.commit()
    session.refresh(teacher)

    assert quiz_router._enseignant_sans_classe_scolaire(teacher) is True
    assert quiz_router._contexte_scolaire_quiz(teacher, session) is None
    assert tuteur_router._enseignant_sans_classe_scolaire(teacher) is True
    assert tuteur_router._contexte_scolaire_tuteur(teacher, session) is None

    session.close()
    engine.dispose()


def test_quiz_cible_refuse_un_profil_scolaire_sans_classe_validee():
    engine, session = _session()
    user = Utilisateur(
        nom="Profil lycée incomplet",
        telephone="0340000099",
        mot_de_passe_hash="hash",
        role=RoleUtilisateur.ETUDIANT,
        cycle_education="lycee",
        niveau_scolaire_id=None,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    assert quiz_router._contexte_scolaire_quiz(user, session) == {}

    session.close()
    engine.dispose()


def test_tuteur_ia_utilise_la_classe_et_refuse_un_document_d_un_autre_niveau():
    engine, session = _session()
    _, niveau, serie = _school_catalogue(session)
    user = _user(session, niveau_id=niveau.id, option_id=serie.id)

    contexte = tuteur_router._contexte_scolaire_tuteur(user, session)
    assert contexte["niveau"] == "Terminale"
    assert contexte["cycle_education"] == "lycee"
    assert contexte["niveau_scolaire_id"] == niveau.id
    assert serie.id in contexte["options_compatibles"]

    meme_niveau = SimpleNamespace(
        portee_academique="scolaire",
        niveau_scolaire_id=niveau.id,
        option_scolaire_id=serie.id,
        etablissement_scolaire_id=None,
    )
    autre_niveau = SimpleNamespace(
        portee_academique="scolaire",
        niveau_scolaire_id=niveau.id + 10,
        option_scolaire_id=serie.id,
        etablissement_scolaire_id=None,
    )
    assert tuteur_router._document_scolaire_compatible(meme_niveau, contexte)
    assert not tuteur_router._document_scolaire_compatible(autre_niveau, contexte)

    document_universitaire = SimpleNamespace(portee_academique="universitaire")
    assert tuteur_router._document_compatible_au_tuteur(meme_niveau, user, contexte)
    assert not tuteur_router._document_compatible_au_tuteur(
        document_universitaire, user, contexte
    )

    enseignant = Utilisateur(
        nom="Enseignant secondaire",
        telephone="0340000101",
        mot_de_passe_hash="hash",
        role=RoleUtilisateur.ETUDIANT,
        profil_souhaite="professeur",
        cycle_education="lycee",
        niveau_scolaire_id=None,
        statut_verification_enseignant="en_attente",
    )
    session.add(enseignant)
    session.commit()
    session.refresh(enseignant)
    assert tuteur_router._document_compatible_au_tuteur(
        meme_niveau, enseignant, None
    )
    assert not tuteur_router._document_compatible_au_tuteur(
        document_universitaire, enseignant, None
    )

    session.close()
    engine.dispose()


def test_source_admin_accepte_uniquement_le_domaine_officiel_men():
    assert admin_scolaire_router._url_source_valide(
        "https://www.education.gov.mg/repartition-annuelle-du-programme-scolaire/"
    )
    assert admin_scolaire_router._url_source_valide(
        "https://docs.education.gov.mg/programmes/"
    )
    assert not admin_scolaire_router._url_source_valide(
        "https://example.com/faux-programme"
    )
    assert not admin_scolaire_router._url_source_valide(
        "https://education.gov.mg.example.com/faux"
    )
    assert not admin_scolaire_router._url_source_valide(
        "http://www.education.gov.mg/faux"
    )
    assert not admin_scolaire_router._url_source_valide(
        "javascript:alert(1)"
    )


def test_api_scolaire_n_expose_que_le_referentiel_verifie():
    engine, session = _session()
    referentiel, niveau, option = _school_catalogue(session)

    payload = scolaire_router.obtenir_referentiel_scolaire(session=session)
    classes = scolaire_router.lister_niveaux_scolaires(cycle="lycee", session=session)
    options = scolaire_router.lister_options_scolaires(niveau.id, session=session)

    assert payload["version"]["code"] == referentiel.code
    assert payload["complet"] is False
    assert any(item["code"] == "TERM" for item in classes)
    assert [item["code"] for item in options] == ["D"]
    session.close()
    engine.dispose()


def test_demande_creation_cercle_scolaire_est_stockee_en_attente():
    engine, session = _session()
    _, niveau, option = _school_catalogue(session)
    user = _user(session, niveau_id=niveau.id, option_id=option.id)
    demande = DemandeCreationCercle(
        utilisateur_id=user.id,
        mention_id=None,
        filiere_id=None,
        niveau=None,
        portee_academique="scolaire",
        niveau_scolaire_id=niveau.id,
        option_scolaire_id=option.id,
        nom="Révisions de Terminale D",
        raison="Groupe national pour préparer le baccalauréat.",
    )
    session.add(demande)
    session.commit()
    session.refresh(demande)

    assert demande.statut == StatutDemandeCreationCercle.EN_ATTENTE
    assert demande.portee_academique == "scolaire"
    assert demande.niveau_scolaire_id == niveau.id
    assert demande.filiere_id is None
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


def test_professeur_peut_declarer_plusieurs_cycles_sans_recevoir_de_role_automatique():
    engine, session = _session()
    user = Utilisateur(
        nom="Professeur multi-cycle",
        telephone="0340000098",
        mot_de_passe_hash="hash",
        role=RoleUtilisateur.ETUDIANT,
        profil_souhaite="professeur",
        cycle_education="college",
        statut_verification_enseignant="en_attente",
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    session.add_all([
        CycleEnseigne(utilisateur_id=user.id, cycle_education="college"),
        CycleEnseigne(utilisateur_id=user.id, cycle_education="lycee"),
        CycleEnseigne(utilisateur_id=user.id, cycle_education="universite"),
    ])
    session.commit()

    cycles = session.exec(
        select(CycleEnseigne).where(CycleEnseigne.utilisateur_id == user.id)
    ).all()
    assert {row.cycle_education for row in cycles} == {
        "college", "lycee", "universite"
    }
    session.refresh(user)
    assert user.role == RoleUtilisateur.ETUDIANT
    assert user.statut_verification_enseignant == "en_attente"

    with pytest.raises(IntegrityError):
        session.add(
            CycleEnseigne(utilisateur_id=user.id, cycle_education="college")
        )
        session.commit()
    session.rollback()

    with pytest.raises(IntegrityError):
        session.add(
            CycleEnseigne(utilisateur_id=user.id, cycle_education="primaire")
        )
        session.commit()
    session.rollback()
    session.close()
    engine.dispose()
