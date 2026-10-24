from pathlib import Path

from app.templating import templates


def test_template_quiz_charge_la_feuille_visuelle_sans_styles_inline():
    template = templates.env.get_template("quiz_config.html")
    source, _, _ = templates.env.loader.get_source(templates.env, "quiz_config.html")
    base, _, _ = templates.env.loader.get_source(templates.env, "base.html")

    assert template is not None
    assert "<style" not in source
    assert 'name="mode_quiz"' in source
    assert 'name="niveau"' not in source
    assert 'request.url.path == "/quiz"' in base
    assert "quiz-visual-refresh.css" in base
    assert "version_asset('quiz-visual-refresh.css')" in base


def test_feuille_quiz_definit_des_surfaces_lisibles_en_clair_et_en_sombre():
    css = Path("app/static/quiz-visual-refresh.css").read_text(encoding="utf-8")

    assert 'html[data-theme="sombre"] main[data-page="/quiz"]' in css
    assert "--content-bg" in css
    assert "--content-surface" in css
    assert "background: var(--content-bg) !important" in css
    assert "color: var(--content-text) !important" in css
    assert "color: var(--content-text-muted) !important" in css
    assert ":has(input:checked)" in css


def test_refonte_quiz_conserve_responsive_et_reduction_des_animations():
    css = Path("app/static/quiz-visual-refresh.css").read_text(encoding="utf-8")

    assert "@media (max-width: 900px)" in css
    assert "@media (max-width: 600px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "focus-visible" in css


def test_refonte_quiz_est_limitee_a_la_page_de_generation():
    css = Path("app/static/quiz-visual-refresh.css").read_text(encoding="utf-8")

    assert 'main[data-page="/quiz"] .ai-learning-page' in css
    assert 'main[data-page="/tuteur"]' not in css
