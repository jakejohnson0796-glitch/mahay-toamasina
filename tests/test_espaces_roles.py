from pathlib import Path
from types import SimpleNamespace

from fastapi.responses import RedirectResponse
from sqlmodel import Session, SQLModel, create_engine

from app.models import (
    Cours,
    Devoir,
    InscriptionCours,
    RoleUtilisateur,
    RenduDevoir,
    Seance,
    StatutSeance,
    Utilisateur,
)
from app.routers import classe_router, dashboard_router


ROOT = Path(__file__).resolve().parents[1]


def _database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def _user(nom, telephone, role, statut="non_concerne"):
    return Utilisateur(
        nom=nom,
        telephone=telephone,
        mot_de_passe_hash="hash-test",
        role=role,
        statut_verification_enseignant=statut,
    )


def test_dashboard_enseignant_compte_uniquement_les_donnees_de_ses_cours():
    _engine, session = _database()
    professeur = _user("Professeur A", "0345000101", RoleUtilisateur.PROFESSEUR, "approuve")
    autre_professeur = _user("Professeur B", "0345000102", RoleUtilisateur.PROFESSEUR, "approuve")
    apprenant = _user("Apprenant", "0345000103", RoleUtilisateur.ETUDIANT)
    session.add_all([professeur, autre_professeur, apprenant])
    session.commit()
    session.refresh(professeur)
    session.refresh(autre_professeur)
    session.refresh(apprenant)

    cours_a = Cours(
        nom="Mathématiques",
        matiere="Mathématiques",
        niveau="L1",
        professeur_id=professeur.id,
    )
    cours_b = Cours(
        nom="Physique",
        matiere="Physique",
        niveau="L2",
        professeur_id=autre_professeur.id,
    )
    session.add_all([cours_a, cours_b])
    session.commit()
    session.refresh(cours_a)
    session.refresh(cours_b)

    session.add_all([
        InscriptionCours(cours_id=cours_a.id, utilisateur_id=apprenant.id),
        InscriptionCours(cours_id=cours_b.id, utilisateur_id=apprenant.id),
        Seance(
            cours_id=cours_a.id,
            titre="Séance planifiée",
            nom_salle_livekit="espace-prof-a",
            statut=StatutSeance.PLANIFIEE,
        ),
    ])
    devoir_a = Devoir(cours_id=cours_a.id, titre="Devoir à corriger")
    devoir_b = Devoir(cours_id=cours_b.id, titre="Devoir d'un autre professeur")
    session.add_all([devoir_a, devoir_b])
    session.commit()
    session.refresh(devoir_a)
    session.refresh(devoir_b)
    session.add_all([
        RenduDevoir(
            devoir_id=devoir_a.id,
            utilisateur_id=apprenant.id,
            chemin_fichier="rendus/a.pdf",
            nom_fichier_original="a.pdf",
        ),
        RenduDevoir(
            devoir_id=devoir_b.id,
            utilisateur_id=apprenant.id,
            chemin_fichier="rendus/b.pdf",
            nom_fichier_original="b.pdf",
        ),
    ])
    session.commit()

    donnees = dashboard_router.donnees_dashboard_enseignant(session, professeur)

    assert donnees["statistiques_enseignant"] == {
        "cours": 1,
        "inscriptions": 1,
        "seances_planifiees": 1,
        "copies_a_corriger": 1,
    }
    assert [item["cours"].nom for item in donnees["cours_enseignes"]] == ["Mathématiques"]
    assert donnees["cours_enseignes"][0]["inscrits"] == 1


def test_espace_classe_reserve_aux_enseignants_verifies():
    approuve = SimpleNamespace(
        role=RoleUtilisateur.PROFESSEUR,
        statut_verification_enseignant="approuve",
    )
    en_attente = SimpleNamespace(
        role=RoleUtilisateur.PROFESSEUR,
        statut_verification_enseignant="en_attente",
    )
    eleve = SimpleNamespace(
        role=RoleUtilisateur.ETUDIANT,
        statut_verification_enseignant="non_concerne",
    )

    assert classe_router._est_professeur(approuve)
    assert not classe_router._est_professeur(en_attente)
    assert not classe_router._est_professeur(eleve)


def test_un_enseignant_ne_peut_pas_ouvrir_mon_parcours(monkeypatch):
    enseignant = SimpleNamespace(role=RoleUtilisateur.PROFESSEUR)
    monkeypatch.setattr(
        dashboard_router,
        "utilisateur_courant",
        lambda request, session: enseignant,
    )

    response = dashboard_router.page_mon_parcours(
        SimpleNamespace(),
        session=SimpleNamespace(),
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_dashboard_et_navigation_ont_deux_experiences_distinctes():
    dashboard_router_source = (ROOT / "app" / "routers" / "dashboard_router.py").read_text(encoding="utf-8")
    teacher_template = (ROOT / "app" / "templates" / "dashboard_enseignant.html").read_text(encoding="utf-8")
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    style = (ROOT / "app" / "static" / "dashboard-enseignant.css").read_text(encoding="utf-8")
    classe_template = (ROOT / "app" / "templates" / "classe_liste.html").read_text(encoding="utf-8")

    assert '"dashboard_enseignant.html"' in dashboard_router_source
    assert 'utilisateur.role == RoleUtilisateur.PROFESSEUR' in dashboard_router_source
    assert 'href="/enseignant/harmonisation"' in teacher_template
    assert 'href="/classe"' in teacher_template
    assert "Ta routine du jour" not in teacher_template
    assert 'utilisateur.role == "professeur"' in base
    assert 'href="/mon-parcours"' in base
    assert "@media(max-width:560px)" in style
    assert "prefers-reduced-motion:reduce" in style
    assert "Espace enseignant · Gestion pédagogique" in classe_template
    assert "Organise tes cours et accompagne tes classes." in classe_template
    assert "Guide enseignant" in classe_template
    assert 'href="/quiz"' in classe_template
    assert "Quiz IA" in classe_template
