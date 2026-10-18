from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_chaque_grand_espace_a_un_bandeau_visuel_contextuel():
    template = (ROOT / "app" / "templates" / "components" / "visuel_page.html").read_text(encoding="utf-8")

    # Le bandeau est inclus depuis base.html : ces familles couvrent les parcours publics,
    # d'apprentissage, de collaboration, de compte et d'administration.
    for route in (
        'chemin == "/"',
        'chemin == "/dashboard"',
        'chemin.startswith("/jeu-cerebral")',
        'chemin.startswith("/documents")',
        'chemin.startswith("/quiz")',
        'chemin.startswith("/tuteur")',
        'chemin.startswith("/classe")',
        'chemin.startswith("/universites")',
        'chemin.startswith("/cercles")',
        'chemin.startswith("/mes-revisions")',
        'chemin.startswith("/defis")',
        'chemin.startswith("/notifications")',
        'chemin.startswith("/securite")',
        'chemin.startswith("/admin")',
        'chemin.startswith("/abonnement")',
        'chemin.startswith("/sponsoring")',
        'chemin.startswith("/faq")',
        'chemin == "/mode-emploi"',
        '"/cadre-legal"',
        'chemin == "/a-propos"',
    ):
        assert route in template, f"Règle de visuel absente : {route}"

    assert 'class="visuel-page-global"' in template
    assert 'loading="eager"' in template\n    assert 'fetchpriority="high"' in template
    assert 'decoding="async"' in template
    assert 'aria-hidden="true"' in template


def test_illustrations_utilisees_sont_locales_et_presentes():
    template = (ROOT / "app" / "templates" / "components" / "visuel_page.html").read_text(encoding="utf-8")
    for chemin in (
        "site/hero-campus.svg",
        "site/community.svg",
        "site/documents.svg",
        "site/quiz.svg",
        "site/tuteur.svg",
        "site/classe.svg",
        "site/universite.svg",
        "site/study-books.svg",
        "jeu-cerebral/brain-hero.webp",
    ):
        assert chemin in template, f"Illustration locale non référencée : {chemin}"
        assert (ROOT / "app" / "static" / "images" / chemin).is_file(), f"Fichier manquant : {chemin}"


def test_bandeaux_visuels_sont_traduits_en_malagasy():
    dictionnaire = (ROOT / "app" / "static" / "js" / "langue.js").read_text(encoding="utf-8")
    for phrase in (
        "Pause cérébrale",
        "Ton tuteur IA",
        "Protéger ton compte",
        "Un cadre clair et responsable",
        "Bien utiliser MITARIDALA",
    ):
        assert phrase in dictionnaire
