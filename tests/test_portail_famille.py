from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine, select
from sqlalchemy.pool import StaticPool
from jinja2 import Environment, FileSystemLoader

from app.models import (
    Cours,
    Devoir,
    EvenementLienResponsableEleve,
    InscriptionCours,
    LienResponsableEleve,
    PointagePresence,
    RoleUtilisateur,
    RenduDevoir,
    Seance,
    StatutPointage,
    Utilisateur,
)
from app.routers.famille_router import construire_portail_famille
from app.admin_security import action_admin_protegee
from app.responsable_portal import chemin_autorise_responsable

ROOT = Path(__file__).resolve().parents[1]


def _utilisateur(nom, telephone, role=None, profil="eleve"):
    if role is None:
        role = (
            RoleUtilisateur.RESPONSABLE
            if profil == "responsable"
            else RoleUtilisateur.ETUDIANT
        )
    return Utilisateur(
        nom=nom,
        telephone=telephone,
        mot_de_passe_hash="hash-test",
        role=role,
        profil_souhaite=profil,
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


def test_portail_ne_retourne_que_les_eleves_rattaches_au_responsable(db):
    admin = _utilisateur("Admin", "03400000001", RoleUtilisateur.ADMIN)
    parent_a = _utilisateur("Parent A", "03400000002", profil="responsable")
    parent_b = _utilisateur("Parent B", "03400000003", profil="responsable")
    enfant_a = _utilisateur("Élève A", "03400000004")
    enfant_b = _utilisateur("Élève B", "03400000005")
    db.add_all([admin, parent_a, parent_b, enfant_a, enfant_b])
    db.commit()
    for user in (admin, parent_a, parent_b, enfant_a, enfant_b):
        db.refresh(user)

    db.add_all([
        LienResponsableEleve(
            responsable_id=parent_a.id,
            eleve_id=enfant_a.id,
            type_lien="parent",
            statut="actif",
            verifie_par_id=admin.id,
        ),
        LienResponsableEleve(
            responsable_id=parent_b.id,
            eleve_id=enfant_b.id,
            type_lien="parent",
            statut="actif",
            verifie_par_id=admin.id,
        ),
    ])
    db.commit()

    resultats = construire_portail_famille(db, parent_a.id)
    assert [item["eleve"].id for item in resultats] == [enfant_a.id]
    assert all(item["eleve"].id != enfant_b.id for item in resultats)


def test_portail_exclut_les_liens_revoques(db):
    admin = _utilisateur("Admin", "03400000011", RoleUtilisateur.ADMIN)
    parent = _utilisateur("Parent", "03400000012", profil="responsable")
    enfant = _utilisateur("Élève", "03400000013")
    db.add_all([admin, parent, enfant])
    db.commit()
    for user in (admin, parent, enfant):
        db.refresh(user)
    db.add(LienResponsableEleve(
        responsable_id=parent.id,
        eleve_id=enfant.id,
        type_lien="tuteur_legal",
        statut="revoque",
        verifie_par_id=admin.id,
    ))
    db.commit()

    assert construire_portail_famille(db, parent.id) == []


def test_portail_partage_uniquement_les_notes_publiees_et_pointages_connus(db):
    admin = _utilisateur("Admin", "03400000021", RoleUtilisateur.ADMIN)
    parent = _utilisateur("Parent", "03400000022", profil="responsable")
    eleve = _utilisateur("Élève", "03400000023")
    prof = _utilisateur("Prof", "03400000024", RoleUtilisateur.PROFESSEUR)
    db.add_all([admin, parent, eleve, prof])
    db.commit()
    for user in (admin, parent, eleve, prof):
        db.refresh(user)

    lien = LienResponsableEleve(
        responsable_id=parent.id,
        eleve_id=eleve.id,
        type_lien="parent",
        statut="actif",
        verifie_par_id=admin.id,
    )
    cours = Cours(
        nom="Mathématiques",
        matiere="Mathématiques",
        niveau="Terminale",
        professeur_id=prof.id,
    )
    db.add_all([lien, cours])
    db.commit()
    db.refresh(cours)

    db.add(InscriptionCours(cours_id=cours.id, utilisateur_id=eleve.id))
    seance_pointee = Seance(
        cours_id=cours.id,
        titre="Algèbre",
        nom_salle_livekit="famille-test-presence",
    )
    seance_sans_pointage = Seance(
        cours_id=cours.id,
        titre="Géométrie",
        nom_salle_livekit="famille-test-sans-pointage",
    )
    devoir_publie = Devoir(
        cours_id=cours.id,
        titre="Contrôle publié",
        bareme=20,
        coefficient=2,
    )
    devoir_brouillon = Devoir(
        cours_id=cours.id,
        titre="Correction en attente",
        bareme=20,
        coefficient=1,
    )
    db.add_all([seance_pointee, seance_sans_pointage, devoir_publie, devoir_brouillon])
    db.commit()
    for obj in (seance_pointee, seance_sans_pointage, devoir_publie, devoir_brouillon):
        db.refresh(obj)

    db.add(PointagePresence(
        seance_id=seance_pointee.id,
        utilisateur_id=eleve.id,
        statut=StatutPointage.PRESENT,
    ))
    db.add_all([
        RenduDevoir(
            devoir_id=devoir_publie.id,
            utilisateur_id=eleve.id,
            chemin_fichier="rendus/publie.pdf",
            nom_fichier_original="publie.pdf",
            note=15,
            appreciation_prof="Bon travail",
            date_correction=__import__("datetime").datetime(2026, 10, 1),
        ),
        RenduDevoir(
            devoir_id=devoir_brouillon.id,
            utilisateur_id=eleve.id,
            chemin_fichier="rendus/attente.pdf",
            nom_fichier_original="attente.pdf",
            note=None,
        ),
    ])
    db.commit()

    resultats = construire_portail_famille(db, parent.id)
    assert len(resultats) == 1
    cours_info = resultats[0]["cours"][0]
    assert cours_info["nb_notes"] == 1
    assert cours_info["notes"][0]["devoir"].titre == "Contrôle publié"
    assert cours_info["moyenne"] == 15
    assert cours_info["presences"]["present"] == 1
    assert cours_info["nb_seances"] == 2
    assert cours_info["nb_pointages"] == 1
    assert cours_info["presences"]["absent"] == 0


def test_modele_interdit_un_rattachement_de_soi_a_soi(db):
    utilisateur = _utilisateur("Compte", "03400000031", profil="responsable")
    db.add(utilisateur)
    db.commit()
    db.refresh(utilisateur)
    lien = LienResponsableEleve(
        responsable_id=utilisateur.id,
        eleve_id=utilisateur.id,
        type_lien="parent",
        verifie_par_id=utilisateur.id,
    )
    db.add(lien)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_inscription_responsable_et_templates_famille_sont_coherents():
    auth = (ROOT / "app" / "routers" / "auth_router.py").read_text(encoding="utf-8")
    ui = (ROOT / "app" / "static" / "js" / "auth-ui.js").read_text(encoding="utf-8")
    register = (ROOT / "app" / "templates" / "register.html").read_text(encoding="utf-8")
    family_router = (ROOT / "app" / "routers" / "famille_router.py").read_text(encoding="utf-8")

    assert 'mode_responsable: str = Form("")' in auth
    assert 'profil_demande = "responsable"' in auth
    assert "role = RoleUtilisateur.RESPONSABLE" in auth
    assert 'return RedirectResponse("/famille", status_code=303)' in auth
    assert 'id="mode_responsable"' in register
    assert 'modeResponsable.addEventListener("change", actualiser)' in ui
    assert 'LienResponsableEleve.statut == "actif"' in family_router
    assert "NoteSeance" not in family_router
    assert 'class EvenementLienResponsableEleve' in (ROOT / "app" / "models.py").read_text(encoding="utf-8")
    assert "EvenementLienResponsableEleve" in family_router
    assert 'eleve.profil_souhaite != "eleve"' in family_router
    assert "responsable.role != RoleUtilisateur.RESPONSABLE" in family_router
    assert action_admin_protegee("/admin/responsables-eleves/associer") is True
    assert action_admin_protegee("/famille") is False


def test_templates_portail_famille_compilent():
    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"))
    assert env.get_template("famille_portail.html") is not None
    assert env.get_template("admin_responsables_eleves.html") is not None


def test_journal_famille_conserve_validation_revocation_et_reactivation(db):
    admin = _utilisateur("Admin", "03400000041", RoleUtilisateur.ADMIN)
    parent = _utilisateur("Parent", "03400000042", profil="responsable")
    enfant = _utilisateur("Élève", "03400000043")
    db.add_all([admin, parent, enfant])
    db.commit()
    for utilisateur in (admin, parent, enfant):
        db.refresh(utilisateur)

    lien = LienResponsableEleve(
        responsable_id=parent.id,
        eleve_id=enfant.id,
        type_lien="parent",
        statut="actif",
        verifie_par_id=admin.id,
    )
    db.add(lien)
    db.commit()
    db.refresh(lien)
    db.add_all([
        EvenementLienResponsableEleve(lien_id=lien.id, acteur_id=admin.id, action="validation", type_lien="parent"),
        EvenementLienResponsableEleve(lien_id=lien.id, acteur_id=admin.id, action="revocation", type_lien="parent"),
        EvenementLienResponsableEleve(lien_id=lien.id, acteur_id=admin.id, action="reactivation", type_lien="parent"),
    ])
    db.commit()

    actions = db.exec(
        select(EvenementLienResponsableEleve.action)
        .where(EvenementLienResponsableEleve.lien_id == lien.id)
        .order_by(EvenementLienResponsableEleve.id)
    ).all()
    assert actions == ["validation", "revocation", "reactivation"]


def test_les_references_famille_sont_anonymisables_lors_d_une_suppression_de_compte():
    assert LienResponsableEleve.__table__.c.responsable_id.nullable is True
    assert LienResponsableEleve.__table__.c.eleve_id.nullable is True
    assert LienResponsableEleve.__table__.c.verifie_par_id.nullable is True
    assert EvenementLienResponsableEleve.__table__.c.acteur_id.nullable is True
    admin_router = (ROOT / "app" / "routers" / "admin_router.py").read_text(encoding="utf-8")
    assert "PointagePresence.utilisateur_id == utilisateur_id" in admin_router
    assert "PointagePresence.saisi_par_id == utilisateur_id" in admin_router
    assert 'action="revocation"' in admin_router


def test_compte_responsable_est_cloisonne_aux_routes_famille_et_securite():
    assert chemin_autorise_responsable("GET", "/famille", 42) is True
    assert chemin_autorise_responsable("GET", "/securite", 42) is True
    assert chemin_autorise_responsable("POST", "/deconnexion", 42) is True
    assert chemin_autorise_responsable("GET", "/static/auth.css", 42) is True
    assert chemin_autorise_responsable("GET", "/classe", 42) is False
    assert chemin_autorise_responsable("POST", "/classe/devoirs/rendus/1/corriger", 42) is False
    assert chemin_autorise_responsable("GET", "/famille/42", 42) is False
