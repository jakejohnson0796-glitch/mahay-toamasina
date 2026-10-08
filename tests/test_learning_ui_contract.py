from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_revision_interface_expose_un_parcours_visuel():
    html = read("app/templates/mes_revisions.html")
    assert "learning-command" in html
    assert "learning-command--revision" in html
    assert 'href="/quiz"' in html
    assert 'href="/tuteur"' in html


def test_tuteur_interface_expose_le_parcours_et_des_actions_claires():
    html = read("app/templates/tuteur.html")
    answer = read("app/templates/tuteur_reponse.html")
    assert "learning-command--ai" in html
    assert "Poser une question" in html
    assert "Comprendre" in html
    assert "learning-command--response" in answer
    assert 'id="reponse"' in answer


def test_quiz_interface_expose_les_etapes_et_un_statut_focus():
    config = read("app/templates/quiz_config.html")
    run = read("app/templates/quiz_passer.html")
    result = read("app/templates/quiz_resultat.html")
    js = read("app/static/js/ai-learning.js")
    css = read("app/static/ai-learning.css")
    assert "learning-command--ai" in config
    assert "quiz-focus-strip" in run
    assert "data-quiz-focus-progress" in run
    assert "data-quiz-focus-progress" in js
    assert "learning-command--result" in result
    assert ".quiz-run-topbar" in css
    assert ".ai-correction-card.is-good::before" in css


def test_interface_learning_responsive_et_reduite_en_animation():
    css = read("app/static/ai-learning.css")
    assert "@media(max-width:640px)" in css
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert ".learning-command-item" in css
