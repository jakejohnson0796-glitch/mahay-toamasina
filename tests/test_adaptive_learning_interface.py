from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_modele_et_migration_persistent_la_mission():
    modele = (ROOT / "app/models.py").read_text(encoding="utf-8")
    migration = (ROOT / "alembic/versions/8f3c9a2d7e41_mission_apprentissage_adaptive.py").read_text(encoding="utf-8")
    assert "class MissionApprentissage" in modele
    assert "uq_missionapprentissage_utilisateur" in modele
    assert 'down_revision: Union[str, None] = "d4e7f1a9c3b2"' in migration
    assert '"missionapprentissage"' in migration
    assert "derniere_tentative_id" in migration


def test_quiz_et_tuteur_transmettent_etat_de_mission():
    quiz = (ROOT / "app/routers/quiz_router.py").read_text(encoding="utf-8")
    tuteur = (ROOT / "app/routers/tuteur_router.py").read_text(encoding="utf-8")
    assert "mission_id: Optional[int] = Form(None)" in quiz
    assert "mission_id: Optional[int] = Form(None)" in tuteur
    assert "transition_apres_quiz" in quiz
    assert 'mission_adaptative.etape = "pratiquer"' in tuteur


def test_resultat_et_reponse_tuteur_proposent_la_suite():
    resultat = (ROOT / "app/templates/quiz_resultat.html").read_text(encoding="utf-8")
    tuteur = (ROOT / "app/templates/tuteur_reponse.html").read_text(encoding="utf-8")
    assert "Continuer ma mission" in resultat
    assert "Continuer ma mission" in tuteur
    assert 'href="/session-apprentissage"' in resultat
