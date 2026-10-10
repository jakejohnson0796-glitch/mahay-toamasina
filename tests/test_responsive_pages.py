from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
PAGES_CSS = ROOT / "app" / "static" / "responsive-pages.css"


def test_responsive_page_layer_is_loaded_after_foundations_in_head():
    base = BASE.read_text(encoding="utf-8")
    foundation = base.index("/static/responsive-foundation.css")
    pages = base.index("/static/responsive-pages.css")
    head_end = base.index("</head>")
    assert foundation < pages < head_end


def test_learning_pages_collapse_without_fixed_sidebar_columns():
    css = PAGES_CSS.read_text(encoding="utf-8")
    for selector in (
        ".ai-hero,",
        ".ai-generation-grid,",
        ".quiz-run-shell,",
        ".ai-tuteur-layout,",
        ".document-upload-layout",
        ".classe-grid",
        ".quiz-run-sidebar",
    ):
        assert selector in css, selector
    assert "@media (max-width: 900px)" in css
    assert "grid-template-columns: minmax(0, 1fr) !important;" in css
    assert "position: static;" in css


def test_document_circles_and_virtual_classroom_have_narrow_screen_fallbacks():
    css = PAGES_CSS.read_text(encoding="utf-8")
    required = (
        ".doc-grille",
        "grid-template-columns: minmax(0, 1fr);",
        ".cercles-hero-visuel",
        "height: auto !important;",
        ".cercle-card-premium-inner",
        ".classe-salle-stage",
        ".classe-chat",
        "overflow-x: auto;",
        "@media (max-width: 600px)",
        "@media (max-width: 340px)",
    )
    for token in required:
        assert token in css, token


def test_dashboard_and_admin_grids_adapt_for_tablets_and_phones():
    css = PAGES_CSS.read_text(encoding="utf-8")
    assert ".tb-ligne-principale" in css
    assert ".tb-ligne-basse" in css
    assert ".tb-grille-stats" in css
    assert ".ops-stat-grid" in css
    assert ".hub-kpis" in css
    assert "@media (max-width: 1150px)" in css
    assert "@media (max-width: 768px)" in css


def test_math_and_long_uploaded_filenames_do_not_force_page_width():
    css = PAGES_CSS.read_text(encoding="utf-8")
    assert ".katex-display" in css
    assert "overflow-x: auto;" in css
    assert ".document-upload-file-name" in css
    assert "overflow-wrap: anywhere;" in css
