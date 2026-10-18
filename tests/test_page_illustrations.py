from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app" / "templates"
ASSETS = ROOT / "app" / "static" / "images"


def test_bibliotheque_document_affiche_une_miniature_contextuelle():
    template = (TEMPLATES / "documents_list.html").read_text(encoding="utf-8")
    assert 'class="doc-carte-visuel"' in template
    for asset in ("site/study-books.svg", "site/quiz.svg", "site/documents.svg", "site/hero-campus.svg"):
        assert f"/static/images/{asset}" in template
        assert (ASSETS / asset).is_file()


def test_quiz_ia_et_tuteur_ia_ont_une_illustration_dans_leur_hero():
    for filename, asset in (
        ("quiz_config.html", "site/quiz.svg"),
        ("quiz.html", "site/quiz.svg"),
        ("tuteur.html", "site/tuteur.svg"),
    ):
        template = (TEMPLATES / filename).read_text(encoding="utf-8")
        assert 'class="ai-hero-illustration"' in template
        assert f"/static/images/{asset}" in template
        assert (ASSETS / asset).is_file()


def test_classe_virtuelle_et_universites_ont_une_illustration_interne():
    cases = (
        ("classe_liste.html", 'class="classe-hero-art"', "site/classe.svg"),
        ("universites.html", 'class="uni-intro-visuel"', "site/universite.svg"),
    )
    for filename, marker, asset in cases:
        template = (TEMPLATES / filename).read_text(encoding="utf-8")
        assert marker in template
        assert f"/static/images/{asset}" in template
        assert (ASSETS / asset).is_file()


def test_cercles_conserve_les_illustrations_editoriales_deja_integrees():
    template = (TEMPLATES / "cercles_list.html").read_text(encoding="utf-8")
    for asset in (
        "cercles/livre-1.svg",
        "cercles/livre-2.svg",
        "cercles/livre-3.svg",
        "cercles/livre-4.svg",
    ):
        assert f"/static/images/{asset}" in template
        assert (ASSETS / asset).is_file()
