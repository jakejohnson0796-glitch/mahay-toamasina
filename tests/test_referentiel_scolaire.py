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
    Faculte,
    Filiere,
    MatiereScolaire,
    Mention,
    Universite,
    NiveauScolaire,
    OptionScolaire,
    OffreEtablissementScolaire,
    ParcoursTechniqueProfessionnel,
    ProgrammeMatiereScolaire,
    ReferentielScolaire,
    RoleUtilisateur,
    StatutCercle,
    StatutDocument,
    StatutDemandeCreationCercle,
    DemandeCreationCercle,
    MembreCercle,
    RoleMembreCercle,
    TypeDocument,
    Utilisateur,
)
from app import quiz as quiz_module
from app.cercles_scolaires import assurer_cercles_scolaires
from app.routers import admin_scolaire_router, auth_router, cercles_router, documents_router, quiz_router, scolaire_router, tuteur_router
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

def test_normaliser_cycles_enseignes_inclut_le_cycle_principal_et_dedoublonne():
    cycles = auth_router.normaliser_cycles_enseignes(
        " college ",
        ["LYCEE", "lycee", " universite ", ""],
    )
    assert cycles == {"college", "lycee", "universite"}


def test_normaliser_cycles_enseignes_refuse_une_valeur_inconnue():
    assert auth_router.normaliser_cycles_enseignes(
        "lycee",
        ["college", "primaire"],
    ) is None


def test_normaliser_cycles_enseignes_ne_confere_pas_de_cycle_par_defaut():
    assert auth_router.normaliser_cycles_enseignes(None, None) == set()

def test_depot_document_respecte_la_matiere_ciblee_par_un_cercle_scolaire():
    cercle = SimpleNamespace(
        portee_academique="scolaire",
        matiere_scolaire_id=17,
    )
    assert documents_router._matiere_cercle_coherente(cercle, 17) is True
    # Un formulaire sans identifiant peut hériter de la matière du cercle ;
    # le routeur la réhydrate ensuite depuis le référentiel vérifié.
    assert documents_router._matiere_cercle_coherente(cercle, None) is True
    assert documents_router._matiere_cercle_coherente(cercle, 18) is False


def test_depot_document_non_scolaire_n_est_pas_bloque_par_la_matiere_du_cercle():
    cercle_universitaire = SimpleNamespace(
        portee_academique="universitaire",
        matiere_scolaire_id=17,
    )
    cercle_sans_matiere = SimpleNamespace(
        portee_academique="scolaire",
        matiere_scolaire_id=None,
    )
    assert documents_router._matiere_cercle_coherente(cercle_universitaire, 18) is True
    assert documents_router._matiere_cercle_coherente(cercle_sans_matiere, 18) is True
    assert documents_router._matiere_cercle_coherente(None, 18) is True

def _admin_sync_cercles(session: Session, telephone: str = "0340000200") -> Utilisateur:
    admin = Utilisateur(
        nom="Admin synchronisation",
        telephone=telephone,
        mot_de_passe_hash="hash",
        role=RoleUtilisateur.ADMIN,
    )
    session.add(admin)
    session.commit()
    session.refresh(admin)
    return admin


def test_synchronisation_cercles_scolaires_cree_une_hierarchie_separee_et_idempotente():
    engine, session = _session()
    referentiel, niveau, serie = _school_catalogue(session)
    admin = _admin_sync_cercles(session)

    matiere = MatiereScolaire(
        code="MATHS_SYNC_TEST",
        libelle="Mathématiques",
        source_officielle=referentiel.source_officielle,
        statut_validation="verifie",
        est_active=True,
    )
    session.add(matiere)
    session.commit()
    session.refresh(matiere)
    session.add(ProgrammeMatiereScolaire(
        referentiel_id=referentiel.id,
        niveau_id=niveau.id,
        option_id=serie.id,
        matiere_id=matiere.id,
        obligatoire=True,
        source_officielle=referentiel.source_officielle,
        statut_validation="verifie",
    ))
    transversal = CercleEtude(
        nom="Groupe transverse conservé",
        createur_id=admin.id,
        portee_academique="transversal",
        statut=StatutCercle.ACTIF,
    )
    session.add(transversal)
    session.commit()
    session.refresh(transversal)

    premier = assurer_cercles_scolaires(session)
    assert premier["cibles"] == 3  # classe, série, matière de la série
    assert premier["crees"] == 3

    cercles = session.exec(select(CercleEtude).where(
        CercleEtude.portee_academique == "scolaire",
        CercleEtude.statut == StatutCercle.ACTIF,
    )).all()
    assert len(cercles) == 3
    assert all(cercle.synchronise_referentiel for cercle in cercles)
    assert all(cercle.mention_id is None and cercle.filiere_id is None for cercle in cercles)
    assert all(cercle.niveau is None for cercle in cercles)
    assert {cercle.niveau_scolaire_id for cercle in cercles} == {niveau.id}
    assert any(cercle.option_scolaire_id is None and cercle.matiere_scolaire_id is None for cercle in cercles)
    assert any(cercle.option_scolaire_id == serie.id and cercle.matiere_scolaire_id is None for cercle in cercles)
    assert any(cercle.option_scolaire_id == serie.id and cercle.matiere_scolaire_id == matiere.id for cercle in cercles)

    # Une mise à jour du référentiel doit propager les libellés dans les
    # cercles gérés automatiquement sans créer de nouvelle identité.
    niveau.libelle = "Terminale générale"
    session.add(niveau)
    session.commit()
    renommes = assurer_cercles_scolaires(session)
    assert renommes["crees"] == 0
    assert renommes["actualises"] == 3
    assert all("Terminale générale" in cercle.nom for cercle in cercles)

    deuxieme = assurer_cercles_scolaires(session)
    assert deuxieme["crees"] == 0
    assert deuxieme["actualises"] == 0
    assert deuxieme["existants"] == 3
    assert session.get(CercleEtude, transversal.id).portee_academique == "transversal"
    assert session.get(CercleEtude, transversal.id).synchronise_referentiel is False

    session.close()
    engine.dispose()


def test_synchronisation_archive_les_cibles_obsoletes_sans_membres_et_preserve_les_cercles_utilises():
    engine, session = _session()
    referentiel, niveau, serie = _school_catalogue(session)
    admin = _admin_sync_cercles(session, telephone="0340000201")
    matiere = MatiereScolaire(
        code="PHYSIQUE_SYNC_TEST",
        libelle="Physique",
        source_officielle=referentiel.source_officielle,
        statut_validation="verifie",
        est_active=True,
    )
    session.add(matiere)
    session.commit()
    session.refresh(matiere)
    programme = ProgrammeMatiereScolaire(
        referentiel_id=referentiel.id,
        niveau_id=niveau.id,
        option_id=serie.id,
        matiere_id=matiere.id,
        obligatoire=True,
        source_officielle=referentiel.source_officielle,
        statut_validation="verifie",
    )
    session.add(programme)
    session.commit()

    assurer_cercles_scolaires(session)
    cercle_serie = session.exec(select(CercleEtude).where(
        CercleEtude.portee_academique == "scolaire",
        CercleEtude.niveau_scolaire_id == niveau.id,
        CercleEtude.option_scolaire_id == serie.id,
        CercleEtude.matiere_scolaire_id.is_(None),
        CercleEtude.statut == StatutCercle.ACTIF,
    )).one()
    cercle_matiere = session.exec(select(CercleEtude).where(
        CercleEtude.portee_academique == "scolaire",
        CercleEtude.niveau_scolaire_id == niveau.id,
        CercleEtude.option_scolaire_id == serie.id,
        CercleEtude.matiere_scolaire_id == matiere.id,
        CercleEtude.statut == StatutCercle.ACTIF,
    )).one()

    membre = _user(
        session, niveau_id=niveau.id, option_id=serie.id,
        telephone="0340000202",
    )
    session.add(MembreCercle(
        cercle_id=cercle_serie.id,
        utilisateur_id=membre.id,
        role=RoleMembreCercle.MEMBRE,
    ))
    serie.est_active = False
    session.add(serie)
    session.commit()

    rapport = assurer_cercles_scolaires(session)
    session.refresh(cercle_serie)
    session.refresh(cercle_matiere)
    assert cercle_serie.statut == StatutCercle.ACTIF
    assert cercle_matiere.statut == StatutCercle.ARCHIVE
    assert rapport["preserves"] == 1
    assert rapport["archives"] == 1

    # La remise en vigueur de la série réactive le cercle matière archivé
    # au lieu de créer une nouvelle ligne ou de dupliquer son identité.
    serie.est_active = True
    session.add(serie)
    session.commit()
    rapport_retour = assurer_cercles_scolaires(session)
    session.refresh(cercle_matiere)
    assert cercle_matiere.statut == StatutCercle.ACTIF
    assert rapport_retour["reactives"] == 1
    assert session.exec(select(CercleEtude).where(
        CercleEtude.portee_academique == "scolaire",
        CercleEtude.niveau_scolaire_id == niveau.id,
        CercleEtude.option_scolaire_id == serie.id,
        CercleEtude.matiere_scolaire_id == matiere.id,
        CercleEtude.statut == StatutCercle.ACTIF,
    )).all().__len__() == 1

    session.close()
    engine.dispose()

def test_la_base_refuse_de_melanger_cible_scolaire_et_universitaire():
    engine, session = _session()
    _, niveau, _ = _school_catalogue(session)
    admin = _admin_sync_cercles(session, telephone="0340000203")
    mention = Mention(nom="Mention de test séparation")
    session.add(mention)
    session.commit()
    session.refresh(mention)

    # Une cible scolaire ne peut pas stocker une mention universitaire.
    with pytest.raises(IntegrityError):
        session.add(CercleEtude(
            nom="Cible mélangée",
            createur_id=admin.id,
            portee_academique="scolaire",
            niveau_scolaire_id=niveau.id,
            mention_id=mention.id,
        ))
        session.commit()
    session.rollback()

    # Une demande scolaire doit impérativement référencer une classe.
    with pytest.raises(IntegrityError):
        session.add(DemandeCreationCercle(
            utilisateur_id=admin.id,
            portee_academique="scolaire",
            nom="Demande sans classe",
            raison="Test de contrainte.",
        ))
        session.commit()
    session.rollback()

    session.close()
    engine.dispose()

def test_recherche_des_cercles_separe_les_cibles_scolaires_des_universitaires():
    engine, session = _session()
    referentiel, niveau_scolaire, option = _school_catalogue(session)
    admin = _admin_sync_cercles(session, telephone="0340000204")
    eleve = _user(
        session,
        niveau_id=niveau_scolaire.id,
        option_id=option.id,
        telephone="0340000205",
    )

    universite = Universite(nom="Université de test — séparation")
    session.add(universite)
    session.commit()
    session.refresh(universite)
    faculte = Faculte(nom="Faculté de test", universite_id=universite.id)
    mention = Mention(nom="Mention de test — séparation")
    session.add_all([faculte, mention])
    session.commit()
    session.refresh(faculte)
    session.refresh(mention)
    filiere = Filiere(
        nom="Parcours de test",
        faculte_id=faculte.id,
        mention_id=mention.id,
        niveau="L1",
    )
    session.add(filiere)
    session.commit()
    session.refresh(filiere)

    cercle_scolaire = CercleEtude(
        nom="Lycée — Terminale — Série D",
        createur_id=admin.id,
        portee_academique="scolaire",
        niveau_scolaire_id=niveau_scolaire.id,
        option_scolaire_id=option.id,
        statut=StatutCercle.ACTIF,
    )
    cercle_universitaire = CercleEtude(
        nom="Mention de test — Parcours — L1",
        createur_id=admin.id,
        portee_academique="universitaire",
        mention_id=mention.id,
        filiere_id=filiere.id,
        niveau="L1",
        statut=StatutCercle.ACTIF,
    )
    cercle_transversal = CercleEtude(
        nom="Groupe inter-cycles",
        createur_id=admin.id,
        portee_academique="transversal",
        statut=StatutCercle.ACTIF,
    )
    session.add_all([cercle_scolaire, cercle_universitaire, cercle_transversal])
    session.commit()
    session.refresh(cercle_scolaire)
    session.refresh(cercle_universitaire)
    session.refresh(cercle_transversal)

    ids_visibles_eleve = set(session.exec(
        select(CercleEtude.id).where(
            condition_cercles_disponibles(eleve, session)
        )
    ).all())
    assert cercle_scolaire.id in ids_visibles_eleve
    assert cercle_transversal.id in ids_visibles_eleve
    assert cercle_universitaire.id not in ids_visibles_eleve

    etudiant_universitaire = Utilisateur(
        nom="Étudiant universitaire de test",
        telephone="0340000206",
        mot_de_passe_hash="hash",
        role=RoleUtilisateur.ETUDIANT,
        profil_souhaite="eleve",
        cycle_education="universite",
        universite_id=universite.id,
        faculte_id=faculte.id,
        mention_id=mention.id,
        filiere_id=filiere.id,
        niveau="L1",
    )
    session.add(etudiant_universitaire)
    session.commit()
    session.refresh(etudiant_universitaire)

    ids_visibles_universitaire = set(session.exec(
        select(CercleEtude.id).where(
            condition_cercles_disponibles(etudiant_universitaire, session)
        )
    ).all())
    assert cercle_universitaire.id in ids_visibles_universitaire
    assert cercle_transversal.id in ids_visibles_universitaire
    assert cercle_scolaire.id not in ids_visibles_universitaire

    session.close()
    engine.dispose()


def test_catalogue_etfp_et_offres_etablissement_ne_publient_que_les_lignes_verifiees():
    engine, session = _session()
    referentiel, niveau, option = _school_catalogue(session)
    source_men = "https://www.education.gov.mg/repartition-annuelle-du-programme-scolaire/"
    source_metfp = "https://www.metfp.gov.mg/cartographie/"

    etablissement = EtablissementScolaire(
        nom="LTP Toamasina",
        code="METFP-ATSINANANA-LTP-TOAMASINA-TEST",
        type_etablissement="lycee_technique",
        secteur="inconnu",
        region="ATSINANANA",
        commune="Toamasina",
        source_officielle=source_metfp,
        est_verifie=True,
        est_actif=True,
    )
    matiere = MatiereScolaire(
        code="MATHS-ETFP-TEST",
        libelle="Mathématiques",
        source_officielle=source_men,
        statut_validation="verifie",
        est_active=True,
    )
    parcours_verifie = ParcoursTechniqueProfessionnel(
        code="TEST-AGENT-COMPTABLE",
        secteur="Gestion",
        filiere="Gestion comptable",
        metier="Agent comptable",
        source_officielle=source_metfp,
        statut_validation="verifie",
        est_actif=True,
    )
    parcours_attente = ParcoursTechniqueProfessionnel(
        code="TEST-FORMATION-ATTENTE",
        secteur="Industriel",
        filiere="Electronique",
        metier="Technicien test",
        source_officielle=source_metfp,
        statut_validation="a_verifier",
        est_actif=False,
    )
    session.add_all([etablissement, matiere, parcours_verifie, parcours_attente])
    session.commit()
    session.refresh(etablissement)
    session.refresh(matiere)
    session.refresh(parcours_verifie)
    session.refresh(parcours_attente)

    programme = ProgrammeMatiereScolaire(
        referentiel_id=referentiel.id,
        niveau_id=niveau.id,
        option_id=None,
        matiere_id=matiere.id,
        obligatoire=True,
        source_officielle=source_men,
        statut_validation="verifie",
    )
    session.add(programme)
    session.commit()

    offre_matiere = OffreEtablissementScolaire(
        etablissement_id=etablissement.id,
        code_offre="MATIERE-TERM-TEST",
        type_offre="matiere",
        niveau_scolaire_id=niveau.id,
        option_scolaire_id=None,
        matiere_scolaire_id=matiere.id,
        parcours_etfp_id=None,
        annee_scolaire="2026-2027",
        source_officielle=source_men,
        statut_validation="verifie",
        est_active=True,
    )
    offre_attente = OffreEtablissementScolaire(
        etablissement_id=etablissement.id,
        code_offre="FORMATION-ATTENTE-TEST",
        type_offre="formation",
        parcours_etfp_id=parcours_attente.id,
        annee_scolaire="2026-2027",
        source_officielle=source_metfp,
        statut_validation="a_verifier",
        est_active=True,
    )
    session.add_all([offre_matiere, offre_attente])
    session.commit()

    from app.routers.scolaire_router import lister_parcours_etfp, rechercher_offres_etablissement

    parcours_publics = lister_parcours_etfp(
        q=None, secteur=None, limite=50, session=session
    )
    assert [item["id"] for item in parcours_publics] == [parcours_verifie.id]

    offres_publiques = rechercher_offres_etablissement(
        q=None,
        region="ATSINANANA",
        commune=None,
        type_offre=None,
        annee_scolaire=None,
        limite=30,
        session=session,
    )
    assert len(offres_publiques) == 1
    assert offres_publiques[0]["etablissement"]["nom"] == "LTP Toamasina"
    assert offres_publiques[0]["annee_scolaire"] == "2026-2027"
    assert offres_publiques[0]["cible"]["matiere"] == "Mathématiques"

    session.close()
    engine.dispose()


def test_offre_etablissement_refuse_le_melange_formation_et_classe():
    engine, session = _session()
    _, niveau, _ = _school_catalogue(session)
    institution = EtablissementScolaire(
        nom="Centre test",
        code="ETFP-TEST-MIXTE",
        type_etablissement="centre_formation_professionnelle",
        secteur="inconnu",
        region="ATSINANANA",
        source_officielle="https://www.metfp.gov.mg/cartographie",
        est_verifie=True,
        est_actif=True,
    )
    parcours = ParcoursTechniqueProfessionnel(
        code="TEST-PARC",
        secteur="Gestion",
        filiere="Gestion comptable",
        metier="Agent comptable",
        source_officielle="https://www.metfp.gov.mg/cartographie",
        statut_validation="verifie",
        est_actif=True,
    )
    session.add_all([institution, parcours])
    session.commit()
    session.refresh(institution)
    session.refresh(parcours)
    invalide = OffreEtablissementScolaire(
        etablissement_id=institution.id,
        code_offre="FORMATION-CLASSE-INVALIDE",
        type_offre="formation",
        niveau_scolaire_id=niveau.id,
        parcours_etfp_id=parcours.id,
        annee_scolaire="2026-2027",
        source_officielle="https://www.metfp.gov.mg/cartographie",
        statut_validation="a_verifier",
        est_active=True,
    )
    session.add(invalide)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.close()
    engine.dispose()
