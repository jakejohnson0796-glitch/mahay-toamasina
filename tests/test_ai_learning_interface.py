from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def lire(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_base_charge_les_assets_quiz_tuteur():
    base = lire("app/templates/base.html")
    assert 'version_asset(\'ai-learning.css\')' in base
    assert 'version_asset(\'ai-learning.js\')' in base
    assert 'request.url.path.startswith("/quiz")' in base
    assert 'request.url.path.startswith("/tuteur")' in base


def test_pages_quiz_et_tuteur_n_ajoutent_pas_de_style_ou_script_inline():
    paths = [
        "app/templates/quiz_config.html",
        "app/templates/quiz_passer.html",
        "app/templates/quiz_resultat.html",
        "app/templates/quiz_historique.html",
        "app/templates/quiz_reflexion.html",
        "app/templates/quiz.html",
        "app/templates/tuteur.html",
        "app/templates/tuteur_reponse.html",
    ]
    for path in paths:
        template = lire(path)
        assert ' style="' not in template, path
        assert "<script" not in template, path


def test_interface_quiz_contient_navigation_et_progression():
    quiz = lire("app/templates/quiz_passer.html")
    assert "data-quiz-form" in quiz
    assert "data-quiz-nav" in quiz
    assert "data-quiz-progress-fill" in quiz
    assert "data-quiz-submit" in quiz


def test_interface_tuteur_contient_suggestions_et_compteur():
    tuteur = lire("app/templates/tuteur.html")
    assert "data-tuteur-question" in tuteur
    assert "data-tuteur-count" in tuteur
    assert "data-tuteur-prompt" in tuteur
    assert "data-tuteur-form" in tuteur


def test_css_et_js_dedies_exist():
    assert (ROOT / "app/static/ai-learning.css").exists()
    assert (ROOT / "app/static/js/ai-learning.js").exists()
