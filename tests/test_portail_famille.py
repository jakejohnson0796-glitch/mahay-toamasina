from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine, select
from sqlalchemy.pool import StaticPool
from jinja2 import Environment, FileSystemLoader

from app.models import (
    BulletinScolaire,
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
        statut_verification_responsable=(
            "approuve" if role == RoleUtilisateur.RESPONSABLE else "non_concerne"
        ),
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



def test_portail_famille_regroupe_les_lectures_sql_pour_plusieurs_enfants_et_cours(db):
    admin = _utilisateur("Admin", "03400000101", RoleUtilisateur.ADMIN)
    parent = _utilisateur("Parent", "03400000102", profil="responsable")
    eleves = [
        _utilisateur("Élève A", "03400000103"),
        _utilisateur("Élève B", "03400000104"),
    ]
    professeur = _utilisateur("Professeur", "03400000105", RoleUtilisateur.PROFESSEUR)
    db.add_all([admin, parent, professeur, *eleves])
    db.commit()
    for utilisateur in (admin, parent, professeur, *eleves):
        db.refresh(utilisateur)

    cours = [
        Cours(nom="Mathématiques", matiere="Mathématiques", niveau="Terminale", professeur_id=professeur.id),
        Cours(nom="Physique", matiere="Physique", niveau="Terminale", professeur_id=professeur.id),
    ]
    db.add_all(cours)
    db.commit()
    for item in cours:
        db.refresh(item)

    liens = [
        LienResponsableEleve(
            responsable_id=parent.id,
            eleve_id=eleve.id,
            type_lien="parent",
            statut="actif",
            verifie_par_id=admin.id,
        )
        for eleve in eleves
    ]
    inscriptions = [
        InscriptionCours(cours_id=classe.id, utilisateur_id=eleve.id)
        for eleve in eleves
        for classe in cours
    ]
    devoirs = [
        Devoir(cours_id=classe.id, titre=f"Évaluation {classe.nom}", bareme=20, coefficient=1)
        for classe in cours
    ]
    seances = [
        Seance(
            cours_id=classe.id,
            titre=f"Séance {classe.nom}",
            nom_salle_livekit=f"famille-batch-{classe.id}",
        )
        for classe in cours
    ]
    db.add_all([*liens, *inscriptions, *devoirs, *seances])
    db.commit()
    for seance in seances:
        db.refresh(seance)

    db.add(PointagePresence(
        seance_id=seances[0].id,
        utilisateur_id=eleves[0].id,
        statut=StatutPointage.PRESENT,
    ))
    db.commit()

    requetes_select = []

    def compter_select(_connexion, _curseur, instruction, _parametres, _contexte, _executemany):
        if instruction.lstrip().upper().startswith("SELECT"):
            requetes_select.append(instruction)

    moteur = db.get_bind()
    event.listen(moteur, "before_cursor_execute", compter_select)
    try:
        resultats = construire_portail_famille(db, parent.id)
    finally:
        event.remove(moteur, "before_cursor_execute", compter_select)

    assert len(resultats) == 2
    assert all(len(enfant["cours"]) == 2 for enfant in resultats)
    assert sum(enfant["cours"][0]["nb_seances"] for enfant in resultats) == 2
    # 10 lectures fixes pour tout le jeu de données; ce nombre ne croît pas
    # avec le nombre d'enfants ou de cours.
    assert len(requetes_select) <= 10


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


def test_portail_famille_calcule_les_moyennes_ponderees_par_periode_et_exclut_les_brouillons(db):
    admin = _utilisateur("Admin périodes", "03400000901", RoleUtilisateur.ADMIN)
    parent = _utilisateur("Parent périodes", "03400000902", profil="responsable")
    eleve = _utilisateur("Élève périodes", "03400000903")
    prof = _utilisateur("Prof périodes", "03400000904", RoleUtilisateur.PROFESSEUR)
    db.add_all([admin, parent, eleve, prof])
    db.commit()
    for user in (admin, parent, eleve, prof):
        db.refresh(user)

    cours = Cours(
        nom="Mathématiques", matiere="Mathématiques",
        niveau="Terminale", professeur_id=prof.id,
    )
    db.add(cours)
    db.commit()
    db.refresh(cours)
    db.add_all([
        LienResponsableEleve(
            responsable_id=parent.id, eleve_id=eleve.id, type_lien="parent",
            statut="actif", verifie_par_id=admin.id,
        ),
        InscriptionCours(cours_id=cours.id, utilisateur_id=eleve.id),
    ])
    devoirs = [
        Devoir(cours_id=cours.id, titre="T1 - devoir 1", bareme=20, coefficient=1, periode="T1"),
        Devoir(cours_id=cours.id, titre="T1 - devoir 2", bareme=20, coefficient=2, periode="T1"),
        Devoir(cours_id=cours.id, titre="T2 - devoir", bareme=20, coefficient=1, periode="T2"),
        Devoir(cours_id=cours.id, titre="T3 - brouillon", bareme=20, coefficient=1, periode="T3"),
    ]
    db.add_all(devoirs)
    db.commit()
    for devoir in devoirs:
        db.refresh(devoir)

    from datetime import datetime

    rendus = [
        RenduDevoir(
            devoir_id=devoirs[0].id, utilisateur_id=eleve.id,
            chemin_fichier="rendus/t1-1.pdf", nom_fichier_original="t1-1.pdf",
            note=16, date_correction=datetime(2026, 10, 2),
        ),
        RenduDevoir(
            devoir_id=devoirs[1].id, utilisateur_id=eleve.id,
            chemin_fichier="rendus/t1-2.pdf", nom_fichier_original="t1-2.pdf",
            note=10, date_correction=datetime(2026, 10, 10),
        ),
        RenduDevoir(
            devoir_id=devoirs[2].id, utilisateur_id=eleve.id,
            chemin_fichier="rendus/t2.pdf", nom_fichier_original="t2.pdf",
            note=18, date_correction=datetime(2026, 11, 1),
        ),
        RenduDevoir(
            devoir_id=devoirs[3].id, utilisateur_id=eleve.id,
            chemin_fichier="rendus/t3-brouillon.pdf", nom_fichier_original="t3-brouillon.pdf",
            note=20, date_correction=None,
        ),
    ]
    db.add_all(rendus)
    db.commit()

    resultat = construire_portail_famille(db, parent.id)
    info = resultat[0]["cours"][0]

    assert info["moyennes_periode"] == [
        {"periode": "T2", "moyenne": 18.0, "nb_notes": 1},
        {"periode": "T1", "moyenne": 12.0, "nb_notes": 2},
    ]
    assert info["moyenne"] == 13.5
    assert all(item["periode"] != "T3" for item in info["moyennes_periode"])



def test_portail_famille_ne_montre_que_les_bulletins_publies_des_enfants_lies(db):
    admin = _utilisateur("Admin bulletin", "03400000911", RoleUtilisateur.ADMIN)
    parent = _utilisateur("Parent bulletin", "03400000912", profil="responsable")
    enfant = _utilisateur("Élève bulletin", "03400000913")
    autre_eleve = _utilisateur("Autre élève bulletin", "03400000914")
    prof = _utilisateur("Prof bulletin", "03400000915", RoleUtilisateur.PROFESSEUR)
    db.add_all([admin, parent, enfant, autre_eleve, prof])
    db.commit()
    for user in (admin, parent, enfant, autre_eleve, prof):
        db.refresh(user)

    cours = Cours(
        nom="Physique", matiere="Physique", niveau="Première",
        professeur_id=prof.id,
    )
    db.add(cours)
    db.commit()
    db.refresh(cours)
    db.add_all([
        LienResponsableEleve(
            responsable_id=parent.id, eleve_id=enfant.id,
            type_lien="parent", statut="actif", verifie_par_id=admin.id,
        ),
        InscriptionCours(cours_id=cours.id, utilisateur_id=enfant.id),
        InscriptionCours(cours_id=cours.id, utilisateur_id=autre_eleve.id),
        BulletinScolaire(
            cours_id=cours.id, utilisateur_id=enfant.id, periode="T1",
            statut="publie", snapshot_json='{"version":1,"evaluations":[],"periode":"T1","matiere":"Physique","cours":"Physique","moyenne":15,"nb_notes":1}',
        ),
        BulletinScolaire(
            cours_id=cours.id, utilisateur_id=enfant.id, periode="T2",
            statut="brouillon", snapshot_json="{}",
        ),
        BulletinScolaire(
            cours_id=cours.id, utilisateur_id=autre_eleve.id, periode="T1",
            statut="publie", snapshot_json='{"version":1,"evaluations":[],"periode":"T1","matiere":"Physique","cours":"Physique","moyenne":18,"nb_notes":1}',
        ),
    ])
    db.commit()

    resultats = construire_portail_famille(db, parent.id)
    assert len(resultats) == 1
    assert [item["bulletin"].periode for item in resultats[0]["bulletins"]] == ["T1"]
    assert resultats[0]["bulletins"][0]["snapshot"]["moyenne"] == 15
    assert resultats[0]["moyennes_bulletins_periode"] == [
        {"periode": "T1", "moyenne": 15.0, "nb_matieres": 1}
    ]

    # Les bulletins publiés restent consultables après le retrait de l'élève
    # du cours ; l'historique scolaire ne dépend pas de l'inscription courante.
    inscriptions = db.exec(
        select(InscriptionCours).where(
            InscriptionCours.cours_id == cours.id,
            InscriptionCours.utilisateur_id == enfant.id,
        )
    ).all()
    for inscription in inscriptions:
        db.delete(inscription)
    db.commit()
    resultats_historiques = construire_portail_famille(db, parent.id)
    assert resultats_historiques[0]["cours"] == []
    assert [item["bulletin"].periode for item in resultats_historiques[0]["bulletins"]] == ["T1"]



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
    assert "est_demande_responsable = True" in auth
    assert "role = RoleUtilisateur.ETUDIANT" in auth
    assert 'statut_verification_responsable=("en_attente" if est_demande_responsable else "non_concerne")' in auth
    assert "profil_validation_requise(utilisateur)" in auth
    assert 'return RedirectResponse("/famille", status_code=303)' in auth
    assert 'id="mode_responsable"' in register
    assert 'modeResponsable.addEventListener("change", actualiser)' in ui
    assert 'roleField.hidden = estResponsable' in ui
    assert 'LienResponsableEleve.statut == "actif"' in family_router
    assert "NoteSeance" not in family_router
    assert 'class EvenementLienResponsableEleve' in (ROOT / "app" / "models.py").read_text(encoding="utf-8")
    assert "EvenementLienResponsableEleve" in family_router
    assert 'eleve.profil_souhaite != "eleve"' in family_router
    assert "responsable.role != RoleUtilisateur.RESPONSABLE" in family_router
    assert 'identifiant_eleve: str = Form("")' in family_router
    assert 'Utilisateur.identifiant_connexion == identifiant_eleve_nettoye' in family_router
    assert 'RESPONSABLE = "responsable"' in (ROOT / "app" / "models.py").read_text(encoding="utf-8")
    assert "chemin_autorise_responsable" in (
        ROOT / "app" / "force_password_change.py"
    ).read_text(encoding="utf-8")
    force_middleware = (ROOT / "app" / "force_password_change.py").read_text(encoding="utf-8")
    assert force_middleware.index("utilisateur.doit_changer_mot_de_passe") < force_middleware.index("est_responsable")
    assert action_admin_protegee("/admin/responsables-eleves/associer") is True
    assert action_admin_protegee("/famille") is False


def test_templates_portail_famille_compilent():
    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"))
    assert env.get_template("famille_portail.html") is not None
    assert env.get_template("admin_responsables_eleves.html") is not None
    source = (ROOT / "app" / "templates" / "famille_portail.html").read_text(encoding="utf-8")
    assert "Résultats par période" in source
    assert "info.moyennes_periode" in source


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
    assert chemin_autorise_responsable("POST", "/securite/2fa/demarrer", 42) is True
    assert chemin_autorise_responsable("POST", "/securite/universite", 42) is False
    assert chemin_autorise_responsable("GET", "/static/auth.css", 42) is True
    assert chemin_autorise_responsable("GET", "/sw.js", 42) is True
    assert chemin_autorise_responsable("GET", "/classe", 42) is False
    force_middleware = (ROOT / "app" / "force_password_change.py").read_text(encoding="utf-8")
    assert "utilisateur.role != RoleUtilisateur.ADMIN" in force_middleware
    assert chemin_autorise_responsable("POST", "/classe/devoirs/rendus/1/corriger", 42) is False
    assert chemin_autorise_responsable("GET", "/famille/42", 42) is False
