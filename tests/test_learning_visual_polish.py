"""Regression checks for the premium Quiz, Tutor and study-circle UI layer."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
POLISH = ROOT / "app" / "static" / "learning-polish.css"


def test_learning_polish_is_loaded_only_for_learning_routes_after_existing_styles():
    base = BASE.read_text(encoding="utf-8")
    conditional = (
        'request.url.path.startswith("/quiz") or '
        'request.url.path.startswith("/tuteur") or '
        'request.url.path.startswith("/cercles")'
    )
    assert conditional in base
    link = '/static/learning-polish.css?v={{ version_asset(\'learning-polish.css\') }}'
    assert base.count(link) == 1
    assert base.index("/static/experience-refresh.css") < base.index(link) < base.index("</head>")
    assert base.index("/static/ai-learning.css") < base.index(link)
    assert "/static/js/rendu_ia.js" in base


def test_quiz_visual_contract_covers_configuration_question_choices_and_results():
    css = POLISH.read_text(encoding="utf-8")
    for selector in (
        ".ai-learning-page .ai-hero",
        ".ai-learning-page .learning-command-item.is-active",
        ".ai-learning-page .ai-quicknav a",
        ".ai-learning-page .ai-form-card",
        ".ai-learning-page .quiz-question-card",
        ".ai-learning-page .quiz-choice:has(input:checked)",
        ".ai-learning-page .ai-result-summary",
        ".ai-learning-page .ai-correction-card",
    ):
        assert selector in css, selector


def test_tutor_visual_contract_covers_chat_prompts_answer_and_history():
    css = POLISH.read_text(encoding="utf-8")
    for selector in (
        ".ai-learning-page .ai-chat-card",
        ".ai-learning-page .ai-chat-avatar",
        ".ai-learning-page .ai-prompt:hover",
        ".ai-learning-page .ai-textarea-wrap textarea:focus",
        ".ai-learning-page .ai-answer-header",
        ".ai-learning-page .ai-markdown-content",
        ".ai-learning-page .ai-tuteur-history-card:hover",
        ".ai-learning-page .ai-remediation-card",
    ):
        assert selector in css, selector


def test_circle_list_and_chat_have_distinct_visual_polish():
    css = POLISH.read_text(encoding="utf-8")
    for selector in (
        ".cercles-page-shell .cercles-hero-visuel",
        ".cercles-page-shell .cercles-hero-stats",
        ".cercles-page-shell .carte-recherche-cercles",
        ".cercles-page-shell .cercle-card-premium:hover",
        ".cercles-page-shell .cercles-visibilite-card:hover",
        ".contenu-clair .entete-cercle",
        ".contenu-clair .message.message-moi .message-corps",
        ".contenu-clair .barre-composition",
        ".contenu-clair .etat-vide-chat",
    ):
        assert selector in css, selector


def test_learning_polish_preserves_dark_theme_mobile_and_accessibility():
    css = POLISH.read_text(encoding="utf-8")
    required = (
        'html[data-theme="sombre"]',
        "@media (max-width: 1000px)",
        "@media (max-width: 700px)",
        "@media (prefers-reduced-motion: reduce)",
        "min-height: 3rem",
        "overflow-wrap: anywhere",
    )
    for token in required:
        assert token in css, token


def test_learning_polish_css_braces_are_balanced():
    css = POLISH.read_text(encoding="utf-8")
    depth = 0
    for char in css:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "CSS contains an unmatched closing brace"
    assert depth == 0, "CSS contains an unmatched opening brace"


def test_quiz_tutor_and_circle_content_templates_remain_in_place():
    quiz = (ROOT / "app" / "templates" / "quiz_config.html").read_text(encoding="utf-8")
    tutor = (ROOT / "app" / "templates" / "tuteur.html").read_text(encoding="utf-8")
    quiz_pass = (ROOT / "app" / "templates" / "quiz_passer.html").read_text(encoding="utf-8")
    circle_chat = (ROOT / "app" / "templates" / "cercle_chat.html").read_text(encoding="utf-8")
    assert 'action="/quiz/generer"' in quiz
    assert 'action="/tuteur/demander"' in tutor
    assert "data-rendu" in quiz_pass
    assert "data-rendu" in tutor
    assert 'id="form-chat"' in circle_chat
    assert 'action="/cercles/{{ cercle.id }}/message-fichier"' in circle_chat
