"""Tests des bulletins officiels, calculs, PDF et droits familiaux."""

from datetime import datetime
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

from app.bulletins import construire_snapshot_bulletin, generer_pdf_bulletin, generer_pdf_bulletin_general, lire_snapshot_bulletin
from app.models import (
    BulletinScolaire,
    BulletinScolaireEvenement,
    Cours,
    Devoir,
    LienResponsableEleve,
    PointagePresence,
    RoleUtilisateur,
    RenduDevoir,
    Seance,
    StatutPointage,
    Utilisateur,
)
from app.responsable_portal import chemin_autorise_responsable
from app.admin_security import action_admin_protegee
from app.routers.bulletin_router import responsable_autorise_bulletin
from app.routers.admin_router import (
    _nettoyer_bulletins_pour_suppression_compte,
    _cascade_supprimer_cours,
)


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


def _utilisateur(nom, telephone, role=RoleUtilisateur.ETUDIANT, profil="eleve"):
    return Utilisateur(
        nom=nom,
        telephone=telephone,
        mot_de_passe_hash="hash-test",
        role=role,
        profil_souhaite=profil,
        statut_verification_enseignant="approuve" if role == RoleUtilisateur.PROFESSEUR else "non_concerne",
    )


def test_snapshot_bulletin_pondere_les_notes_corrigees_et_exclut_les_brouillons(db):
    prof = _utilisateur("Enseignant", "03400001001", RoleUtilisateur.PROFESSEUR)
    eleve = _utilisateur("Élève", "03400001002")
    db.add_all([prof, eleve])
    db.commit()
    db.refresh(prof)
    db.refresh(eleve)

    cours = Cours(
        nom="Mathématiques - Terminale",
        matiere="Mathématiques",
        niveau="Terminale",
        professeur_id=prof.id,
    )
    db.add(cours)
    db.commit()
    db.refresh(cours)

    devoirs = [
        Devoir(cours_id=cours.id, titre="Algèbre", bareme=20, coefficient=1, periode="T1"),
        Devoir(cours_id=cours.id, titre="Géométrie", bareme=20, coefficient=2, periode="t1"),
        Devoir(cours_id=cours.id, titre="Analyse", bareme=20, coefficient=1, periode="T1"),
        Devoir(cours_id=cours.id, titre="Physique", bareme=20, coefficient=1, periode="T2"),
    ]
    db.add_all(devoirs)
    db.commit()
    for devoir in devoirs:
        db.refresh(devoir)

    db.add_all([
        RenduDevoir(
            devoir_id=devoirs[0].id, utilisateur_id=eleve.id,
            chemin_fichier="rendus/algebre.pdf", nom_fichier_original="algebre.pdf",
            note=16, date_correction=datetime(2026, 10, 2),
            appreciation_prof="Méthode maîtrisée",
        ),
        RenduDevoir(
            devoir_id=devoirs[1].id, utilisateur_id=eleve.id,
            chemin_fichier="rendus/geometrie.pdf", nom_fichier_original="geometrie.pdf",
            note=10, date_correction=datetime(2026, 10, 10),
        ),
        RenduDevoir(
            devoir_id=devoirs[2].id, utilisateur_id=eleve.id,
            chemin_fichier="rendus/analyse.pdf", nom_fichier_original="analyse.pdf",
            note=20, date_correction=None,
        ),
        RenduDevoir(
            devoir_id=devoirs[3].id, utilisateur_id=eleve.id,
            chemin_fichier="rendus/physique.pdf", nom_fichier_original="physique.pdf",
            note=19, date_correction=datetime(2026, 11, 1),
        ),
    ])
    seance_1 = Seance(cours_id=cours.id, titre="Séance 1", nom_salle_livekit="bulletin-test-1")
    seance_2 = Seance(cours_id=cours.id, titre="Séance 2", nom_salle_livekit="bulletin-test-2")
    db.add_all([seance_1, seance_2])
    db.commit()
    db.refresh(seance_1)
    db.add_all([
        PointagePresence(seance_id=seance_1.id, utilisateur_id=eleve.id, statut=StatutPointage.PRESENT),
        PointagePresence(seance_id=seance_2.id, utilisateur_id=eleve.id, statut=StatutPointage.ABSENT),
    ])
    db.commit()

    snapshot = construire_snapshot_bulletin(
        db, cours, eleve, "T1", "Continue tes efforts.",
        publie_le=datetime(2026, 11, 20, 10, 30),
    )
    assert snapshot["moyenne"] == 12.0
    assert snapshot["nb_notes"] == 2
    assert [item["evaluation"] for item in snapshot["evaluations"]] == ["Algèbre", "Géométrie"]
    assert snapshot["presences"] == {
        "present": 1, "absent": 1, "retard": 0, "excuse": 0,
    }
    assert snapshot["nb_pointages"] == 2
    assert snapshot["nb_seances"] == 2
    assert snapshot["appreciation_generale"] == "Continue tes efforts."


def test_pdf_est_genere_depuis_le_snapshot_et_les_snapshots_invalides_sont_refuses(db):
    prof = _utilisateur("Prof PDF", "03400001101", RoleUtilisateur.PROFESSEUR)
    eleve = _utilisateur("Élève PDF", "03400001102")
    db.add_all([prof, eleve])
    db.commit()
    db.refresh(prof)
    db.refresh(eleve)
    cours = Cours(
        nom="Français", matiere="Français", niveau="Seconde",
        professeur_id=prof.id,
    )
    db.add(cours)
    db.commit()
    db.refresh(cours)
    devoir = Devoir(
        cours_id=cours.id, titre="Rédaction", bareme=20,
        coefficient=1, periode="Semestre 1",
    )
    db.add(devoir)
    db.commit()
    db.refresh(devoir)
    db.add(RenduDevoir(
        devoir_id=devoir.id, utilisateur_id=eleve.id,
        chemin_fichier="rendus/francais.pdf", nom_fichier_original="francais.pdf",
        note=17, date_correction=datetime(2026, 10, 5),
    ))
    db.commit()

    snapshot = construire_snapshot_bulletin(db, cours, eleve, "Semestre 1", "Très bon travail.")
    pdf = generer_pdf_bulletin(snapshot)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1000
    assert lire_snapshot_bulletin(__import__("json").dumps(snapshot))["moyenne"] == 17
    assert lire_snapshot_bulletin('{"version":1,"evaluations":"invalide"}') is None
    assert lire_snapshot_bulletin("{") is None


def test_suppression_compte_efface_ses_bulletins_et_anonymise_les_acteurs(db):
    compte_supprime = _utilisateur("Compte supprimé", "03400001401", RoleUtilisateur.PROFESSEUR)
    autre_prof = _utilisateur("Autre professeur", "03400001402", RoleUtilisateur.PROFESSEUR)
    eleve_conserve = _utilisateur("Élève conservé", "03400001403")
    db.add_all([compte_supprime, autre_prof, eleve_conserve])
    db.commit()
    for user in (compte_supprime, autre_prof, eleve_conserve):
        db.refresh(user)
    cours = Cours(nom="Sciences", matiere="Sciences", niveau="3e", professeur_id=autre_prof.id)
    db.add(cours)
    db.commit()
    db.refresh(cours)
    bulletin_eleve_supprime = BulletinScolaire(
        cours_id=cours.id, utilisateur_id=compte_supprime.id, periode="T1",
        cree_par_id=compte_supprime.id, publie_par_id=compte_supprime.id,
        statut="publie", snapshot_json='{"version":1,"evaluations":[]}',
    )
    bulletin_conserve = BulletinScolaire(
        cours_id=cours.id, utilisateur_id=eleve_conserve.id, periode="T1",
        cree_par_id=compte_supprime.id, publie_par_id=compte_supprime.id,
        statut="publie", snapshot_json='{"version":1,"evaluations":[]}',
    )
    db.add_all([bulletin_eleve_supprime, bulletin_conserve])
    db.commit()
    db.refresh(bulletin_eleve_supprime)
    db.refresh(bulletin_conserve)
    id_bulletin_supprime = bulletin_eleve_supprime.id
    id_bulletin_conserve = bulletin_conserve.id
    db.add_all([
        BulletinScolaireEvenement(
            bulletin_id=id_bulletin_supprime, acteur_id=compte_supprime.id, action="publication",
            details_json='{}',
        ),
        BulletinScolaireEvenement(
            bulletin_id=id_bulletin_conserve, acteur_id=compte_supprime.id, action="publication",
            details_json='{}',
        ),
    ])
    db.commit()

    _nettoyer_bulletins_pour_suppression_compte(db, compte_supprime.id)
    db.commit()
    assert db.get(BulletinScolaire, id_bulletin_supprime) is None
    conserve = db.get(BulletinScolaire, id_bulletin_conserve)
    assert conserve is not None
    assert conserve.cree_par_id is None
    assert conserve.publie_par_id is None
    evenements = db.exec(
        select(BulletinScolaireEvenement).where(
            BulletinScolaireEvenement.bulletin_id == id_bulletin_conserve
        )
    ).all()
    assert len(evenements) == 1
    assert evenements[0].acteur_id is None
    db.delete(compte_supprime)
    db.commit()


def test_suppression_cours_efface_les_bulletins_et_le_journal_associe(db):
    prof = _utilisateur("Prof cours supprimé", "03400001501", RoleUtilisateur.PROFESSEUR)
    eleve = _utilisateur("Élève cours supprimé", "03400001502")
    db.add_all([prof, eleve])
    db.commit()
    db.refresh(prof)
    db.refresh(eleve)
    cours = Cours(nom="Cours supprimé", matiere="SVT", niveau="6e", professeur_id=prof.id)
    db.add(cours)
    db.commit()
    db.refresh(cours)
    bulletin = BulletinScolaire(
        cours_id=cours.id, utilisateur_id=eleve.id, periode="T2",
        statut="brouillon",
    )
    db.add(bulletin)
    db.commit()
    db.refresh(bulletin)
    db.add(BulletinScolaireEvenement(
        bulletin_id=bulletin.id, acteur_id=prof.id, action="creation", details_json="{}",
    ))
    db.commit()
    bulletin_id = bulletin.id

    _cascade_supprimer_cours(db, cours.id)
    db.commit()
    assert db.get(Cours, cours.id) is None
    assert db.get(BulletinScolaire, bulletin_id) is None
    assert db.exec(
        select(BulletinScolaireEvenement).where(
            BulletinScolaireEvenement.bulletin_id == bulletin_id
        )
    ).all() == []


def test_pdf_bulletin_general_regroupe_plusieurs_matieres_et_calcule_la_moyenne_par_matiere():
    snapshots = [
        {
            "version": 1, "cours_id": 1, "eleve": "Élève Exemple",
            "cours": "Mathématiques - Terminale", "matiere": "Mathématiques",
            "niveau": "Terminale", "periode": "T1", "professeur": "Mme A",
            "moyenne": 12.0, "nb_notes": 3, "poids_total": 4,
            "evaluations": [{"evaluation": "Algèbre", "note": 12, "bareme": 20, "note_sur_20": 12}],
            "appreciation_generale": "Bonne progression.",
            "presences": {"present": 3, "absent": 0, "retard": 0, "excuse": 0},
            "nb_pointages": 3, "nb_seances": 3,
        },
        {
            "version": 1, "cours_id": 2, "eleve": "Élève Exemple",
            "cours": "Français - Terminale", "matiere": "Français",
            "niveau": "Terminale", "periode": "t1", "professeur": "M. B",
            "moyenne": 16.0, "nb_notes": 2, "poids_total": 2,
            "evaluations": [{"evaluation": "Rédaction", "note": 16, "bareme": 20, "note_sur_20": 16}],
            "appreciation_generale": "Très bon travail.",
            "presences": {"present": 2, "absent": 1, "retard": 0, "excuse": 0},
            "nb_pointages": 3, "nb_seances": 3,
        },
    ]
    pdf = generer_pdf_bulletin_general(snapshots, "T1")
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1500


def test_telechargement_refuse_si_le_lien_familial_est_revoque_ou_pour_un_autre_enfant(db):
    admin = _utilisateur("Admin", "03400001201", RoleUtilisateur.ADMIN)
    parent = _utilisateur("Parent", "03400001202", RoleUtilisateur.RESPONSABLE, "responsable")
    autre_parent = _utilisateur("Autre parent", "03400001203", RoleUtilisateur.RESPONSABLE, "responsable")
    eleve = _utilisateur("Élève", "03400001204")
    prof = _utilisateur("Professeur", "03400001205", RoleUtilisateur.PROFESSEUR)
    db.add_all([admin, parent, autre_parent, eleve, prof])
    db.commit()
    for user in (admin, parent, autre_parent, eleve, prof):
        db.refresh(user)

    cours = Cours(
        nom="Histoire", matiere="Histoire", niveau="Première",
        professeur_id=prof.id,
    )
    db.add(cours)
    db.commit()
    db.refresh(cours)
    bulletin = BulletinScolaire(
        cours_id=cours.id,
        utilisateur_id=eleve.id,
        periode="T1",
        statut="publie",
        snapshot_json='{"version":1,"evaluations":[]}',
    )
    lien = LienResponsableEleve(
        responsable_id=parent.id,
        eleve_id=eleve.id,
        statut="actif",
        type_lien="parent",
        verifie_par_id=admin.id,
    )
    db.add_all([bulletin, lien])
    db.commit()
    db.refresh(bulletin)

    assert responsable_autorise_bulletin(db, parent, bulletin) is True
    assert responsable_autorise_bulletin(db, autre_parent, bulletin) is False

    lien.statut = "revoque"
    db.add(lien)
    db.commit()
    assert responsable_autorise_bulletin(db, parent, bulletin) is False

    eleve.role = RoleUtilisateur.RESPONSABLE
    eleve.profil_souhaite = "responsable"
    db.add(eleve)
    db.commit()
    assert responsable_autorise_bulletin(db, eleve, bulletin) is False


def test_une_reouverture_peut_conserver_l_ancienne_version_dans_le_journal(db):
    prof = _utilisateur("Prof audit", "03400001301", RoleUtilisateur.PROFESSEUR)
    eleve = _utilisateur("Élève audit", "03400001302")
    db.add_all([prof, eleve])
    db.commit()
    db.refresh(prof)
    db.refresh(eleve)
    cours = Cours(nom="SVT", matiere="SVT", niveau="3e", professeur_id=prof.id)
    db.add(cours)
    db.commit()
    db.refresh(cours)

    bulletin = BulletinScolaire(
        cours_id=cours.id, utilisateur_id=eleve.id, periode="T1",
        statut="brouillon",
    )
    db.add(bulletin)
    db.commit()
    db.refresh(bulletin)
    ancien_snapshot = '{"version":1,"moyenne":14.5,"evaluations":[]}'
    bulletin.statut = "brouillon"
    bulletin.snapshot_json = "{}"
    db.add(bulletin)
    from app.models import BulletinScolaireEvenement
    db.add(BulletinScolaireEvenement(
        bulletin_id=bulletin.id,
        acteur_id=prof.id,
        action="reouverture",
        details_json='{"motif":"Correction","snapshot_precedent":' + __import__("json").dumps(ancien_snapshot) + "}",
    ))
    db.commit()
    evenement = db.query(BulletinScolaireEvenement).filter_by(bulletin_id=bulletin.id).one()
    assert "14.5" in evenement.details_json



def test_liste_blanche_responsable_autorise_uniquement_le_pdf_general_de_periode():
    assert chemin_autorise_responsable("GET", "/famille/bulletins/periode/telecharger", 7) is True
    assert chemin_autorise_responsable("HEAD", "/famille/bulletins/periode/telecharger", 7) is True
    assert chemin_autorise_responsable("POST", "/famille/bulletins/periode/telecharger", 7) is False


def test_actions_admin_bulletin_exigent_la_confirmation_admin():
    assert action_admin_protegee("/classe/12/bulletins/creer") is True
    assert action_admin_protegee("/classe/bulletins/42/modifier") is True
    assert action_admin_protegee("/classe/bulletins/42/publier") is True
    assert action_admin_protegee("/classe/bulletins/42/reouvrir") is True
    assert action_admin_protegee("/classe/bulletins/42/consulter") is False
    assert action_admin_protegee("/classe/12/etudiants") is False



def test_liste_blanche_responsable_limite_le_telechargement_a_un_id_numerique():
    assert chemin_autorise_responsable("GET", "/famille/bulletins/42/telecharger", 7) is True
    assert chemin_autorise_responsable("HEAD", "/famille/bulletins/42/telecharger", 7) is True
    assert chemin_autorise_responsable("POST", "/famille/bulletins/42/telecharger", 7) is False
    assert chemin_autorise_responsable("GET", "/famille/bulletins/abc/telecharger", 7) is False
    assert chemin_autorise_responsable("GET", "/famille/bulletins/42", 7) is False
    assert chemin_autorise_responsable("GET", "/famille/42", 7) is False
