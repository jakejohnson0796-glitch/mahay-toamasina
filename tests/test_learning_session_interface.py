from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mission_template_contient_les_trois_etapes():
    text = (ROOT / "app/templates/session_apprentissage.html").read_text(encoding="utf-8")
    for label in ("Comprendre", "Pratiquer", "Vérifier"):
        assert label in text
    assert "mission-apprentissage" in text


def test_mission_styles_are_responsive():
    text = (ROOT / "app/static/student-hub.css").read_text(encoding="utf-8")
    assert ".mission-apprentissage" in text
    assert "@media(max-width:760px)" in text
    assert "prefers-reduced-motion" in text


def test_route_mission_importe_son_moteur():
    text = (ROOT / "app/routers/revisions_router.py").read_text(encoding="utf-8")
    assert "from .. import learning_session" in text
    assert "learning_session.construire_mission" in text
