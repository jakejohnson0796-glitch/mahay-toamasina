"""Regression checks for the study-circle hierarchy and sidebar preferences."""

from pathlib import Path

from app.models import CercleEtude, Filiere
from app.referentiel_academique import cercle_est_national, type_cercle

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
SIDEBAR_CSS = ROOT / "app" / "static" / "sidebar.css"
LANGUAGE_JS = ROOT / "app" / "static" / "js" / "langue.js"
CIRCLES_TEMPLATE = ROOT / "app" / "templates" / "cercles_list.html"
CIRCLES_ROUTER = ROOT / "app" / "routers" / "cercles_router.py"
ACADEMIC_ROUTER = ROOT / "app" / "routers" / "academique_router.py"


def test_language_and_appearance_controls_live_in_one_sidebar_preferences_area():
    base = BASE.read_text(encoding="utf-8")
    js = LANGUAGE_JS.read_text(encoding="utf-8")
    css = SIDEBAR_CSS.read_text(encoding="utf-8")

    assert base.count('id="select-langue"') == 1
    assert base.count('id="bouton-theme"') == 1
    assert 'class="tb-sidebar-preferences"' in base
    assert 'aria-label="Préférences de langue"' in base
    preferences = base.split('class="tb-sidebar-preferences"', 1)[1].split("</section>", 1)[0]
    assert 'id="bouton-theme"' in preferences
    assert 'id="select-langue"' in preferences
    assert base.index('class="tb-sidebar-preferences"') > base.index('class="tb-sidebar-nav"')
    assert 'var SELECTEUR = "#select-langue";' in js
    assert ".tb-sidebar-preferences" in css
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_legacy_circle_without_denormalized_mention_recovers_its_pathway():
    circle = CercleEtude(
        id=5001,
        nom="Finance L3 legacy",
        createur_id=1,
        filiere_id=900,
        mention_id=None,
        niveau="L3",
    )
    pathway = Filiere(
        id=900,
        nom="Finance",
        faculte_id=80,
        mention_id=70,
        niveau=None,
    )
    assert type_cercle(circle, pathway) == "parcours"
    assert cercle_est_national(circle, pathway)


def test_circle_with_a_different_mention_or_level_is_marked_for_review():
    pathway = Filiere(
        id=901,
        nom="Finance",
        faculte_id=80,
        mention_id=70,
        niveau="L3",
    )
    mention_mismatch = CercleEtude(
        id=5002,
        nom="Incoherent mention",
        createur_id=1,
        filiere_id=901,
        mention_id=71,
        niveau="L3",
    )
    level_mismatch = CercleEtude(
        id=5003,
        nom="Incoherent level",
        createur_id=1,
        filiere_id=901,
        mention_id=70,
        niveau="M1",
    )
    assert type_cercle(mention_mismatch, pathway) == "incomplet"
    assert type_cercle(level_mismatch, pathway) == "incomplet"
    assert not cercle_est_national(mention_mismatch, pathway)
    assert not cercle_est_national(level_mismatch, pathway)


def test_circle_creation_rejects_partial_or_mismatched_academic_hierarchies():
    router = CIRCLES_ROUTER.read_text(encoding="utf-8")
    assert "hierarchy_selectionnee" in router
    assert 'erreur=niveau_requis' in router
    assert 'erreur=mention_requise' in router
    assert 'erreur=mention_parcours_incoherents' in router
    assert "filiere_canonique_pour_cercle(session, filiere, niveau_nettoye)" in router


def test_circle_card_types_use_readable_labels_and_the_avatar_has_one_class_attribute():
    template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
    assert "Parcours national" in template
    assert "Tronc commun" in template
    assert "Groupe libre" in template
    assert "À vérifier" in template
    assert 'class="carte-claire-avatar carte-claire-avatar-couleur-{{ info.cercle.id % 5 }}"' in template
    assert 'class="carte-claire-avatar" aria-hidden="true" class=' not in template


def test_national_pathway_api_checks_canonical_level_active_offers_and_matching_university():
    router = ACADEMIC_ROUTER.read_text(encoding="utf-8")
    assert "niveau not in NIVEAUX" in router
    assert "Universite.est_active == True" in router
    assert "ProgrammeUniversitaire.universite_id == Faculte.universite_id" in router
    assert "ProgrammeUniversitaire.est_active == True" in router
    assert 'actuelle["niveau"] is None and f.niveau == niveau' in router


def test_sidebar_and_css_have_balanced_structure():
    base = BASE.read_text(encoding="utf-8")
    css = SIDEBAR_CSS.read_text(encoding="utf-8")
    assert base.count("<section class=\"tb-sidebar-preferences\"") == 1

    depth = 0
    for char in css:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "CSS contains an unmatched closing brace"
    assert depth == 0, "CSS contains an unmatched opening brace"
