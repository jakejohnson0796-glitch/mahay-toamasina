"""Regression checks for language preferences and circle taxonomy consistency."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
SIDEBAR_CSS = ROOT / "app" / "static" / "sidebar.css"
CIRCLES_TEMPLATE = ROOT / "app" / "templates" / "cercles_list.html"
CIRCLES_ROUTER = ROOT / "app" / "routers" / "cercles_router.py"
ACADEMIC_ROUTER = ROOT / "app" / "routers" / "academique_router.py"
ACADEMIC_REFERENCE = ROOT / "app" / "referentiel_academique.py"


def test_language_selector_is_only_in_account_settings():
    base = BASE.read_text(encoding="utf-8")
    settings = (ROOT / "app" / "templates" / "securite.html").read_text(encoding="utf-8")
    assert "select-langue" not in base
    assert settings.count('id="select-langue-parametres"') == 1
    assert 'class="ops-security-card ops-language-settings" id="language-settings"' in settings
    assert '<option value="fr" data-no-translate>Français</option>' in settings
    assert '<option value="mg" data-no-translate>Malagasy</option>' in settings
    assert '<option value="en" data-no-translate>English</option>' in settings


def test_language_preference_card_is_visible_responsive_and_keyboard_accessible():
    css = (ROOT / "app" / "static" / "interface-polish.css").read_text(encoding="utf-8")
    assert ".ops-language-settings" in css
    assert ".ops-language-settings select:focus-visible" in css
    assert "@media (max-width: 640px)" in css
    assert "var(--content-surface)" in css
    assert "var(--content-text)" in css


def test_circle_labels_use_national_scope_and_human_readable_levels():
    template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
    assert "À l’échelle de Madagascar · Cercles d’étude" in template
    assert 'niveaux_libelles.get(n, n)' in template
    assert 'niveaux_libelles.get(info.cercle.niveau, info.cercle.niveau)' in template
    assert "Parcours national" in template
    assert "Tronc commun" in template
    assert "Référentiel à vérifier" in template
    assert 'class="carte-claire-avatar carte-claire-avatar-couleur-' in template
    assert '<span class="carte-claire-avatar" aria-hidden="true" class=' not in template


def test_creation_route_rejects_partial_or_cross_mention_selections():
    router = CIRCLES_ROUTER.read_text(encoding="utf-8")
    assert "erreur_selection_creation_cercle(" in router
    assert "erreur=parcours_hors_mention" in router
    assert "niveaux_libelles" in router
    assert "type_cercle(cercle, session)" in router
    assert "cercle_est_national(cercle, session)" in router
    assert 'type_cercle(cercle, session) != "libre"' in router


def test_national_course_options_match_the_actual_university_of_the_faculty():
    router = ACADEMIC_ROUTER.read_text(encoding="utf-8")
    assert "Faculte.universite_id == ProgrammeUniversitaire.universite_id" in router
    assert "if not domaine or not domaine.est_active:" in router
    assert "Domaine.est_active == True" in router


def test_legacy_circle_type_is_resolved_from_filiere_and_conflicts_stay_incomplete():
    reference = ACADEMIC_REFERENCE.read_text(encoding="utf-8")
    assert "def type_cercle(cercle: CercleEtude, session: Optional[Session] = None)" in reference
    assert "mention_id = mention_id or filiere.mention_id" in reference
    assert "mention_id != filiere.mention_id" in reference
    assert "def erreur_selection_creation_cercle(" in reference
    assert "mention_compatible_avec_parcours" in reference


def test_circle_filter_css_braces_are_balanced():
    template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
    block = template.split("<style nonce=", 1)[1].split("</style>", 1)[0]
    depth = 0
    for char in block:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "Circle page styles contain an unmatched closing brace"
    assert depth == 0, "Circle page styles contain an unmatched opening brace"


def test_university_catalogue_caveat_is_visible_on_student_screens():
    warning = (
        "Le catalogue présente les formations répertoriées. Il ne confirme pas "
        "à lui seul l’habilitation en vigueur ni l’ouverture des admissions pour "
        "l’année universitaire en cours ; vérifiez les dates et conditions auprès "
        "de votre composante."
    )
    for path in (
        ROOT / "app" / "templates" / "register.html",
        ROOT / "app" / "templates" / "profil_academique.html",
        ROOT / "app" / "templates" / "universites.html",
    ):
        assert warning in path.read_text(encoding="utf-8")
