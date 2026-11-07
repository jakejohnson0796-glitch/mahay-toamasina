from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlmodel import SQLModel, Session, create_engine

from app.institution_access import (
    ROLE_ETUDIANT, ROLE_PROFESSEUR, ROLE_RESPONSABLE,
    assurer_membre, est_inscrit_cours, institution_pour_cours,
    membre_actif, peut_gerer_cours, peut_rejoindre_cours, lister_inscriptions_actives,
)
from app.models import (
    Cours, EtablissementPartenaire, InscriptionCours,
    RoleUtilisateur, Utilisateur,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def creer_compte(db, nom, role=RoleUtilisateur.ETUDIANT):
    compte = Utilisateur(nom=nom, mot_de_passe_hash="hash-test", role=role)
    db.add(compte)
    db.flush()
    return compte


def creer_etablissement(db, nom, code):
    institution = EtablissementPartenaire(nom=nom, code=code)
    db.add(institution)
    db.flush()
    return institution


def test_les_roles_institutionnels_sont_distincts_des_roles_globaux(db):
    institution = creer_etablissement(db, "Institut A", "INST-A")
    etudiant = creer_compte(db, "Etudiant A")
    membre = assurer_membre(db, institution.id, etudiant.id, ROLE_ETUDIANT)

    assert membre_actif(db, institution.id, etudiant.id, (ROLE_ETUDIANT,)) is membre
    assert membre_actif(db, institution.id, etudiant.id, (ROLE_PROFESSEUR,)) is None
    assert etudiant.role == RoleUtilisateur.ETUDIANT


def test_un_etudiant_d_un_autre_etablissement_ne_peut_pas_rejoindre_ni_voir_le_cours(db):
    inst_a = creer_etablissement(db, "Université A", "UNIV-A")
    inst_b = creer_etablissement(db, "Université B", "UNIV-B")
    professeur = creer_compte(db, "Professeur A")
    etudiant_a = creer_compte(db, "Etudiant A")
    etudiant_b = creer_compte(db, "Etudiant B")
    assurer_membre(db, inst_a.id, professeur.id, ROLE_PROFESSEUR)
    assurer_membre(db, inst_a.id, etudiant_a.id, ROLE_ETUDIANT)
    assurer_membre(db, inst_b.id, etudiant_b.id, ROLE_ETUDIANT)

    cours = Cours(
        nom="Analyse", matiere="Mathématiques", niveau="L1",
        professeur_id=professeur.id, institution_id=inst_a.id,
    )
    db.add(cours)
    db.flush()
    db.add(InscriptionCours(cours_id=cours.id, utilisateur_id=etudiant_a.id))
    # Une inscription incohérente ne doit pas franchir le contrôle du tenant.
    db.add(InscriptionCours(cours_id=cours.id, utilisateur_id=etudiant_b.id))
    db.flush()

    assert peut_rejoindre_cours(db, cours, etudiant_a)
    assert not peut_rejoindre_cours(db, cours, etudiant_b)
    assert est_inscrit_cours(db, cours.id, etudiant_a.id)
    assert not est_inscrit_cours(db, cours.id, etudiant_b.id)


def test_professeur_et_responsable_sont_limites_a_leur_etablissement(db):
    inst_a = creer_etablissement(db, "Université A", "UNIV-A")
    inst_b = creer_etablissement(db, "Université B", "UNIV-B")
    professeur_a = creer_compte(db, "Professeur A")
    professeur_b = creer_compte(db, "Professeur B")
    responsable_a = creer_compte(db, "Responsable A")
    assurer_membre(db, inst_a.id, professeur_a.id, ROLE_PROFESSEUR)
    assurer_membre(db, inst_b.id, professeur_b.id, ROLE_PROFESSEUR)
    assurer_membre(db, inst_a.id, responsable_a.id, ROLE_RESPONSABLE)
    cours = Cours(
        nom="Comptabilité", matiere="Gestion", niveau="L2",
        professeur_id=professeur_a.id, institution_id=inst_a.id,
    )
    db.add(cours)
    db.flush()

    assert peut_gerer_cours(db, cours, professeur_a)
    assert peut_gerer_cours(db, cours, responsable_a)
    assert not peut_gerer_cours(db, cours, professeur_b)


def test_affectation_a_un_etablissement_est_verifiee(db):
    inst_a = creer_etablissement(db, "Université A", "UNIV-A")
    inst_b = creer_etablissement(db, "Université B", "UNIV-B")
    responsable_a = creer_compte(db, "Responsable A")
    assurer_membre(db, inst_a.id, responsable_a.id, ROLE_RESPONSABLE)

    assert institution_pour_cours(db, responsable_a, None) == inst_a.id
    with pytest.raises(ValueError):
        institution_pour_cours(db, responsable_a, inst_b.id)


def test_un_professeur_ayant_plusieurs_etablissements_doit_choisir(db):
    inst_a = creer_etablissement(db, "Université A", "UNIV-A")
    inst_b = creer_etablissement(db, "Université B", "UNIV-B")
    professeur = creer_compte(db, "Professeur itinérant")
    assurer_membre(db, inst_a.id, professeur.id, ROLE_PROFESSEUR)
    assurer_membre(db, inst_b.id, professeur.id, ROLE_PROFESSEUR)

    with pytest.raises(ValueError, match="Choisis l'établissement"):
        institution_pour_cours(db, professeur, None)
    assert institution_pour_cours(db, professeur, inst_b.id) == inst_b.id


def test_un_membre_desactive_perd_immediatement_ses_acces(db):
    institution = creer_etablissement(db, "Université A", "UNIV-A")
    etudiant = creer_compte(db, "Etudiant A")
    membre = assurer_membre(db, institution.id, etudiant.id, ROLE_ETUDIANT)
    cours = Cours(
        nom="Droit", matiere="Droit", niveau="L1",
        professeur_id=etudiant.id, institution_id=institution.id,
    )
    db.add(cours)
    db.flush()
    db.add(InscriptionCours(cours_id=cours.id, utilisateur_id=etudiant.id))
    db.flush()
    assert est_inscrit_cours(db, cours.id, etudiant.id)

    membre.est_actif = False
    db.add(membre)
    db.flush()
    assert not est_inscrit_cours(db, cours.id, etudiant.id)
    assert not peut_rejoindre_cours(db, cours, etudiant)


def test_les_cours_historiques_restent_accessibles_sans_perimetre_institutionnel(db):
    professeur = creer_compte(db, "Professeur historique", RoleUtilisateur.PROFESSEUR)
    etudiant = creer_compte(db, "Etudiant historique")
    cours = Cours(
        nom="Cours historique", matiere="Histoire", niveau="L1",
        professeur_id=professeur.id, institution_id=None,
    )
    db.add(cours)
    db.flush()
    db.add(InscriptionCours(cours_id=cours.id, utilisateur_id=etudiant.id))
    db.flush()

    assert peut_gerer_cours(db, cours, professeur)
    assert peut_rejoindre_cours(db, cours, etudiant)
    assert est_inscrit_cours(db, cours.id, etudiant.id)



def test_un_etablissement_inactif_suspend_toutes_les_appartenances(db):
    institution = creer_etablissement(db, "Institut fermé", "INST-F")
    responsable = creer_compte(db, "Responsable")
    assurer_membre(db, institution.id, responsable.id, ROLE_RESPONSABLE)

    institution.est_actif = False
    db.add(institution)
    db.flush()

    assert membre_actif(db, institution.id, responsable.id, (ROLE_RESPONSABLE,)) is None
    with pytest.raises(ValueError, match="rattachement institutionnel est inactif"):
        institution_pour_cours(db, responsable, None)



def test_un_professeur_global_peut_etre_etudiant_dans_un_autre_tenant(db):
    inst_prof = creer_etablissement(db, "Institut professeur", "INST-P")
    inst_etudiant = creer_etablissement(db, "Institut étudiant", "INST-E")
    compte = creer_compte(db, "Compte double rôle", RoleUtilisateur.PROFESSEUR)
    professeur_cours = creer_compte(db, "Professeur du cours")
    assurer_membre(db, inst_prof.id, compte.id, ROLE_PROFESSEUR)
    assurer_membre(db, inst_etudiant.id, compte.id, ROLE_ETUDIANT)
    assurer_membre(db, inst_etudiant.id, professeur_cours.id, ROLE_PROFESSEUR)

    cours = Cours(
        nom="Cours du soir", matiere="Mathématiques", niveau="L1",
        professeur_id=professeur_cours.id, institution_id=inst_etudiant.id,
    )
    db.add(cours)
    db.flush()

    assert peut_rejoindre_cours(db, cours, compte)
    db.add(InscriptionCours(cours_id=cours.id, utilisateur_id=compte.id))
    db.flush()
    assert est_inscrit_cours(db, cours.id, compte.id)



def test_les_listes_de_classe_excluent_les_inscriptions_d_un_autre_tenant(db):
    inst_a = creer_etablissement(db, "Université A", "UNIV-A")
    inst_b = creer_etablissement(db, "Université B", "UNIV-B")
    professeur = creer_compte(db, "Professeur A")
    etudiant_a = creer_compte(db, "Etudiant A")
    etudiant_b = creer_compte(db, "Etudiant B")
    assurer_membre(db, inst_a.id, professeur.id, ROLE_PROFESSEUR)
    assurer_membre(db, inst_a.id, etudiant_a.id, ROLE_ETUDIANT)
    assurer_membre(db, inst_b.id, etudiant_b.id, ROLE_ETUDIANT)
    cours = Cours(
        nom="Cours isolé", matiere="Mathématiques", niveau="L1",
        professeur_id=professeur.id, institution_id=inst_a.id,
    )
    db.add(cours)
    db.flush()
    db.add_all([
        InscriptionCours(cours_id=cours.id, utilisateur_id=etudiant_a.id),
        InscriptionCours(cours_id=cours.id, utilisateur_id=etudiant_b.id),
    ])
    db.flush()

    lignes = lister_inscriptions_actives(db, cours.id)
    ids = {etudiant.id for _, etudiant in lignes}
    assert ids == {etudiant_a.id}



def test_professeur_independant_sans_affiliation_peut_creer_un_cours_historique(db):
    professeur = creer_compte(db, "Professeur indépendant", RoleUtilisateur.PROFESSEUR)
    assert institution_pour_cours(db, professeur, None) is None



def test_cours_ambigu_reste_en_quarantaine_jusqua_affectation_explicite(db):
    inst_a = creer_etablissement(db, "Université A", "QUAR-A")
    inst_b = creer_etablissement(db, "Université B", "QUAR-B")
    professeur = creer_compte(db, "Professeur multi-établissement", RoleUtilisateur.PROFESSEUR)
    etudiant = creer_compte(db, "Étudiant A", RoleUtilisateur.ETUDIANT)
    assurer_membre(db, inst_a.id, professeur.id, ROLE_PROFESSEUR)
    assurer_membre(db, inst_b.id, professeur.id, ROLE_PROFESSEUR)
    assurer_membre(db, inst_a.id, etudiant.id, ROLE_ETUDIANT)

    cours = Cours(
        nom="Cours historique ambigu",
        matiere="Mathématiques",
        niveau="L1",
        professeur_id=professeur.id,
        affectation_institutionnelle_requise=True,
        code_invitation="AMBIGU123",
    )
    db.add(cours)
    db.flush()
    db.add(InscriptionCours(cours_id=cours.id, utilisateur_id=etudiant.id))
    db.flush()

    admin = creer_compte(db, "Admin global", RoleUtilisateur.ADMIN)
    assert not peut_gerer_cours(db, cours, professeur)
    assert peut_gerer_cours(db, cours, admin)
    assert not peut_rejoindre_cours(db, cours, etudiant)
    assert not est_inscrit_cours(db, cours.id, etudiant.id)
    assert cours.code_invitation == "AMBIGU123"  # conservé, mais inutilisable pendant la quarantaine
    assert lister_inscriptions_actives(db, cours.id) == []

    cours.institution_id = inst_a.id
    cours.affectation_institutionnelle_requise = False
    db.add(cours)
    db.flush()
    assert peut_rejoindre_cours(db, cours, etudiant)
    assert est_inscrit_cours(db, cours.id, etudiant.id)


def test_un_etudiant_desactive_ne_peut_pas_telecharger_sa_copie(db, monkeypatch):
    from app.routers import classe_router
    from app.models import Devoir, RenduDevoir

    institution = creer_etablissement(db, "Université A", "UNIV-DL")
    professeur = creer_compte(db, "Professeur A", RoleUtilisateur.PROFESSEUR)
    etudiant = creer_compte(db, "Etudiant A", RoleUtilisateur.ETUDIANT)
    assurer_membre(db, institution.id, professeur.id, ROLE_PROFESSEUR)
    appartenance = assurer_membre(db, institution.id, etudiant.id, ROLE_ETUDIANT)
    cours = Cours(
        nom="Cours privé", matiere="Droit", niveau="L1",
        professeur_id=professeur.id, institution_id=institution.id,
    )
    db.add(cours)
    db.flush()
    devoir = Devoir(cours_id=cours.id, titre="Devoir")
    db.add(devoir)
    db.flush()
    rendu = RenduDevoir(
        devoir_id=devoir.id,
        utilisateur_id=etudiant.id,
        chemin_fichier="/tmp/rendu-test.pdf",
        nom_fichier_original="rendu.pdf",
    )
    db.add_all([InscriptionCours(cours_id=cours.id, utilisateur_id=etudiant.id), rendu])
    db.flush()
    appartenance.est_actif = False
    db.add(appartenance)
    db.flush()
    monkeypatch.setattr(
        classe_router,
        "utilisateur_courant",
        lambda request, session: etudiant,
    )

    response = classe_router.telecharger_rendu(SimpleNamespace(), rendu.id, db)

    assert response.status_code == 303
    assert response.headers["location"] == f"/classe/{cours.id}"
