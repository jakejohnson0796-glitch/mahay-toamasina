from __future__ import annotations

from collections import Counter

import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.institution_access import (
    ROLE_ETUDIANT,
    assurer_membre,
    cours_ids_etudiant_actifs,
    est_inscrit_cours,
    lister_inscriptions_actives,
    lister_inscriptions_actives_pour_cours,
    lister_cours_gerables,
    lister_cours_etudies,
    membre_actif,
    verrouiller_etablissement,
)
from app.models import (
    Cours,
    EtablissementPartenaire,
    InscriptionCours,
    RoleUtilisateur,
    Utilisateur,
)


@pytest.fixture
def session_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session, engine
    engine.dispose()


def _compte(session: Session, nom: str) -> Utilisateur:
    compte = Utilisateur(
        nom=nom,
        mot_de_passe_hash="hash-test",
        role=RoleUtilisateur.ETUDIANT,
    )
    session.add(compte)
    session.flush()
    return compte


def _etablissement(session: Session, nom: str, code: str) -> EtablissementPartenaire:
    institution = EtablissementPartenaire(nom=nom, code=code)
    session.add(institution)
    session.flush()
    return institution


def _cours(
    session: Session,
    nom: str,
    professeur_id: int,
    institution_id: int | None = None,
    *,
    quarantaine: bool = False,
) -> Cours:
    cours = Cours(
        nom=nom,
        matiere="Mathématiques",
        niveau="L1",
        professeur_id=professeur_id,
        institution_id=institution_id,
        affectation_institutionnelle_requise=quarantaine,
    )
    session.add(cours)
    session.flush()
    return cours


def test_membre_actif_refuse_une_liste_de_roles_vide(session_db):
    session, _engine = session_db
    institution = _etablissement(session, "Institut A", "INST-A")
    compte = _compte(session, "Étudiant A")
    assurer_membre(session, institution.id, compte.id, ROLE_ETUDIANT)

    assert membre_actif(session, institution.id, compte.id, roles=()) is None
    assert membre_actif(session, institution.id, compte.id) is not None


def test_les_listes_de_cours_tenant_sont_filtrees_en_une_requete(session_db):
    session, engine = session_db
    institution_active = _etablissement(session, "Université active", "UNIV-A")
    institution_inactive = _etablissement(session, "Institut suspendu", "INST-I")
    institution_inactive.est_actif = False
    compte = _compte(session, "Étudiant A")

    assurer_membre(session, institution_active.id, compte.id, ROLE_ETUDIANT)
    assurer_membre(session, institution_inactive.id, compte.id, ROLE_ETUDIANT)

    cours_actif = _cours(
        session, "Cours du tenant actif", compte.id, institution_active.id
    )
    cours_suspendu = _cours(
        session, "Cours du tenant suspendu", compte.id, institution_inactive.id
    )
    cours_historique = _cours(session, "Cours historique indépendant", compte.id)
    cours_quarantaine = _cours(
        session, "Cours en quarantaine", compte.id, quarantaine=True
    )
    session.add_all([
        InscriptionCours(cours_id=cours_actif.id, utilisateur_id=compte.id),
        InscriptionCours(cours_id=cours_suspendu.id, utilisateur_id=compte.id),
        InscriptionCours(cours_id=cours_historique.id, utilisateur_id=compte.id),
        InscriptionCours(cours_id=cours_quarantaine.id, utilisateur_id=compte.id),
    ])
    session.flush()

    requetes = Counter()

    def compter_select(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            requetes["select"] += 1

    event.listen(engine, "before_cursor_execute", compter_select)
    try:
        ids = cours_ids_etudiant_actifs(session, compte.id)
        assert ids == sorted([cours_actif.id, cours_historique.id])
        assert est_inscrit_cours(session, cours_actif.id, compte.id)
        assert not est_inscrit_cours(session, cours_suspendu.id, compte.id)
        lignes = lister_inscriptions_actives(session, cours_actif.id)
        assert [utilisateur.id for _inscription, utilisateur in lignes] == [compte.id]
        assert lister_inscriptions_actives(session, cours_suspendu.id) == []
    finally:
        event.remove(engine, "before_cursor_execute", compter_select)

    # Each helper emits a single SELECT, rather than one query per course/member.
    assert requetes["select"] == 5


def test_verrouillage_etablissement_retrouve_uniquement_un_parent_existant(session_db):
    session, _engine = session_db
    institution = _etablissement(session, "Université verrouillée", "UNIV-LOCK")
    assert verrouiller_etablissement(session, institution.id).id == institution.id
    assert verrouiller_etablissement(session, institution.id + 999) is None


def test_listes_cours_gerables_et_etudies_filtrent_les_tenants_en_lot(session_db):
    session, engine = session_db
    inst_a = _etablissement(session, "Université A", "UNIV-A")
    inst_b = _etablissement(session, "Université B", "UNIV-B")
    professeur_a = _compte(session, "Professeur A")
    etudiant_a = _compte(session, "Étudiant A")
    etudiant_b = _compte(session, "Étudiant B")
    assurer_membre(session, inst_a.id, professeur_a.id, "professeur")
    assurer_membre(session, inst_a.id, etudiant_a.id, ROLE_ETUDIANT)
    assurer_membre(session, inst_b.id, etudiant_b.id, ROLE_ETUDIANT)
    cours_a = _cours(session, "Cours A", professeur_a.id, inst_a.id)
    cours_b = _cours(session, "Cours B", professeur_a.id, inst_b.id)
    cours_libre = _cours(session, "Cours libre", professeur_a.id)
    cours_quarantaine = _cours(session, "Cours suspendu", professeur_a.id, inst_a.id, quarantaine=True)
    session.add_all([
        InscriptionCours(cours_id=cours_a.id, utilisateur_id=etudiant_a.id),
        InscriptionCours(cours_id=cours_a.id, utilisateur_id=etudiant_b.id),
        InscriptionCours(cours_id=cours_b.id, utilisateur_id=etudiant_b.id),
        InscriptionCours(cours_id=cours_quarantaine.id, utilisateur_id=etudiant_a.id),
    ])
    session.flush()

    requetes = Counter()

    def compter_select(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            requetes["select"] += 1

    event.listen(engine, "before_cursor_execute", compter_select)
    try:
        gerables = lister_cours_gerables(session, professeur_a)
        etudies = lister_cours_etudies(session, etudiant_a.id)
        lignes = lister_inscriptions_actives_pour_cours(session, [cours_a.id, cours_b.id])
    finally:
        event.remove(engine, "before_cursor_execute", compter_select)

    assert {cours.id for cours in gerables} == {cours_a.id, cours_libre.id}
    assert {cours.id for cours in etudies} == {cours_a.id}
    assert {etudiant.id for _inscription, etudiant in lignes} == {etudiant_a.id, etudiant_b.id}
    assert requetes["select"] == 3


def test_cours_ids_etudiant_actifs_ne_duplique_pas_les_inscriptions_historiques(session_db):
    session, _engine = session_db
    institution = _etablissement(session, "Université doublons", "UNIV-DUP")
    etudiant = _compte(session, "Étudiant doublons")
    assurer_membre(session, institution.id, etudiant.id, ROLE_ETUDIANT)
    cours = _cours(session, "Cours avec doublon", etudiant.id, institution.id)
    session.add_all([
        InscriptionCours(cours_id=cours.id, utilisateur_id=etudiant.id),
        InscriptionCours(cours_id=cours.id, utilisateur_id=etudiant.id),
    ])
    session.flush()

    assert cours_ids_etudiant_actifs(session, etudiant.id) == [cours.id]


def test_responsable_actif_recharge_une_appartenance_modifiee_par_une_autre_session(tmp_path):
    from app.routers.institution_router import responsable_actif
    from app.models import MembreEtablissement

    engine = create_engine(
        f"sqlite:///{tmp_path / 'responsable-refresh.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as initial:
            institution = _etablissement(initial, "Institut actualisé", "INST-REFRESH")
            responsable = _compte(initial, "Responsable actualisé")
            assurer_membre(initial, institution.id, responsable.id, "responsable")
            initial.commit()
            institution_id, responsable_id = institution.id, responsable.id

        with Session(engine) as lecteur, Session(engine) as modificateur:
            assert responsable_actif(lecteur, responsable_id, institution_id)
            # Termine la transaction de lecture tout en gardant les objets dans
            # l'identité map ; l'autre session révoque ensuite le rôle.
            lecteur.commit()
            membre = modificateur.exec(
                select(MembreEtablissement).where(
                    MembreEtablissement.institution_id == institution_id,
                    MembreEtablissement.utilisateur_id == responsable_id,
                )
            ).one()
            membre.est_actif = False
            modificateur.add(membre)
            modificateur.commit()

            assert not responsable_actif(lecteur, responsable_id, institution_id)
    finally:
        engine.dispose()
