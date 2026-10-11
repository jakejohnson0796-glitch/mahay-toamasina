"""Regression checks for language selector placement and academic circle coherence."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
SIDEBAR_CSS = ROOT / "app" / "static" / "sidebar.css"
CIRCLES_TEMPLATE = ROOT / "app" / "templates" / "cercles_list.html"
CIRCLES_ROUTER = ROOT / "app" / "routers" / "cercles_router.py"
ACADEMIC_API = ROOT / "app" / "routers" / "academique_router.py"
CIRCLES_JS = ROOT / "app" / "static" / "js" / "cercles-list.js"


def test_language_selector_is_compact_and_accessible_without_changing_i18n_id():
    base = BASE.read_text(encoding="utf-8")
    css = SIDEBAR_CSS.read_text(encoding="utf-8")
    assert base.count('id="select-langue"') == 1
    assert 'aria-label="Choisir la langue"' in base
    assert 'class="tb-sidebar-langue-globe"' in base
    assert 'class="tb-sidebar-langue-label"' in base
    assert "border-radius: 999px" in css
    assert ".tb-sidebar-langue-label" in css
    assert "body.sidebar-compact .tb-sidebar-langue select" in css
    assert "@media (prefers-reduced-motion:reduce)" in css


def test_circle_creation_rejects_partial_academic_triplets_and_mismatched_mention():
    router = CIRCLES_ROUTER.read_text(encoding="utf-8")
    assert "selection_academique = bool(mention_id_nettoye or filiere_id_nettoye or niveau_nettoye)" in router
    assert "erreur=referentiel_incomplet" in router
    assert "mention_id_nettoye != filiere.mention_id" in router
    assert "erreur=parcours_mention_incoherents" in router


def test_all_circle_cards_use_the_validated_effective_academic_identity():
    router = CIRCLES_ROUTER.read_text(encoding="utf-8")
    assert router.count("contexte_identite_cercle(cercle, session)") >= 2
    template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
    assert "Référentiel à vérifier" in template
    assert 'info.type_cercle == "incomplet"' in template
    assert 'info.type_cercle == "tronc_commun"' in template
    # Do not show a missing/incoherent pathway as if it were tronc commun.
    assert '{% if info.filiere %} · {{ info.filiere.nom }}{% else %} · Tronc commun{% endif %}' not in template


def test_circle_card_has_one_avatar_class_attribute_and_explicit_kind_labels():
    template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
    assert 'class="carte-claire-avatar carte-claire-avatar-couleur-{{ info.cercle.id % 5 }}"' in template
    assert 'class="carte-claire-avatar" aria-hidden="true" class=' not in template
    assert "Parcours national" in template
    assert "Tronc commun" in template
    assert "Groupe libre" in template


def test_national_path_choices_use_active_offers_stable_order_and_valid_levels():
    api = ACADEMIC_API.read_text(encoding="utf-8")
    assert "if niveau and niveau not in NIVEAUX:" in api
    assert "ProgrammeUniversitaire.universite_id == Universite.id" in api
    assert "Universite.est_active == True" in api
    assert "order_by(Filiere.nom, Filiere.niveau.is_(None), Filiere.id)" in api


def test_tronc_commun_help_uses_hidden_attribute_consistently():
    template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
    js = CIRCLES_JS.read_text(encoding="utf-8")
    assert 'id="creation-info-tronc-commun" hidden' in template
    assert 'id="creation-info-tronc-commun" style="display:none;"' not in template
    assert "if (infoTronc) infoTronc.hidden = false;" in js
    assert "if (infoTronc) infoTronc.hidden = true;" in js


def test_circle_stylesheets_and_scripts_are_balanced_or_loaded_by_existing_base():
    base = BASE.read_text(encoding="utf-8")
    template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
    assert '/static/sidebar.css?v={{ version_asset(\'sidebar.css\') }}' in base
    assert "js/cercles-list.js" in template
    css = SIDEBAR_CSS.read_text(encoding="utf-8")
    depth = 0
    for char in css:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "sidebar CSS contains an unmatched closing brace"
    assert depth == 0, "sidebar CSS contains an unmatched opening brace"
