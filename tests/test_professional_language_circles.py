"""Regression checks for locale placement and circle hierarchy consistency."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
SIDEBAR_CSS = ROOT / "app" / "static" / "sidebar.css"
CIRCLES_TEMPLATE = ROOT / "app" / "templates" / "cercles_list.html"
CIRCLES_JS = ROOT / "app" / "static" / "js" / "cercles-list.js"
CIRCLES_ROUTER = ROOT / "app" / "routers" / "cercles_router.py"
ACADEMIC_API = ROOT / "app" / "routers" / "academique_router.py"
ACADEMIC = ROOT / "app" / "referentiel_academique.py"


def test_language_control_is_compact_and_keeps_the_existing_translation_hook():
    base = BASE.read_text(encoding="utf-8")
    css = SIDEBAR_CSS.read_text(encoding="utf-8")
    assert base.count('id="select-langue"') == 1
    assert 'id="select-langue"' in base
    assert 'src="/static/js/langue.js?v={{ version_asset(\'js/langue.js\') }}"' in base
    brand = base.split('<div class="tb-sidebar-marque">', 1)[1].split("</div>", 1)[0]
    assert 'class="tb-sidebar-langue"' in brand
    assert '<option value="fr">FR</option>' in brand
    assert '<option value="mg">MG</option>' in brand
    assert "grid-template-columns:minmax(0,1fr) auto auto" in css
    assert ".tb-sidebar-langue select:focus-visible" in css


def test_circle_form_never_claims_tronc_commun_is_guaranteed_by_an_empty_path_list():
    template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
    js = CIRCLES_JS.read_text(encoding="utf-8")
    assert 'id="creation-info-tronc-commun" hidden' in template
    assert 'id="creation-info-tronc-commun" style="display:none;"' not in template
    assert "Le tronc commun dépend de ta composante" in js
    assert "ce sera un cercle de tronc commun" not in js


def test_circle_creation_rejects_partial_or_mismatched_academic_hierarchies():
    router = CIRCLES_ROUTER.read_text(encoding="utf-8")
    create = router.split('@router.post("/cercles/creer")', 1)[1].split(
        '@router.post("/cercles/{cercle_id}/demander")', 1
    )[0]
    assert "if mention_id_nettoye and not niveau_nettoye:" in create
    assert "if filiere_id_nettoye and not niveau_nettoye:" in create
    assert "if niveau_nettoye and not (mention_id_nettoye or filiere_id_nettoye):" in create
    assert "hierarchie_academique_incoherente" in create
    assert "filiere_canonique_pour_cercle(" in create
    assert "niveau=niveau_nettoye" in create


def test_circle_search_and_cards_use_effective_legacy_mention_and_level():
    router = CIRCLES_ROUTER.read_text(encoding="utf-8")
    template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
    academic = ACADEMIC.read_text(encoding="utf-8")
    assert "func.coalesce(CercleEtude.niveau, Filiere.niveau)" in router
    assert '"niveau_effectif": cercle.niveau or (filiere.niveau if filiere else None)' in router
    assert "type_cercle(cercle, session=session)" in router
    assert "mention_filiere_cercle" in academic
    assert "niveau_filiere_cercle" in academic
    assert "info.niveau_effectif" in template
    assert "Domaine non renseigne" not in template
    assert 'class="carte-claire-avatar carte-claire-avatar-couleur-' in template
    assert 'class="carte-claire-avatar" aria-hidden="true" class=' not in template


def test_national_pathway_endpoint_validates_offers_and_does_not_merge_different_levels():
    api = ACADEMIC_API.read_text(encoding="utf-8")
    endpoint = api.split('@router.get("/mentions/{mention_id}/parcours-nationaux")', 1)[1].split(
        '\ndef lister_filieres(', 1
    )[0]
    assert "if niveau and niveau not in NIVEAUX:" in endpoint
    assert "offre_filiere_active_universite(" in endpoint
    assert "cle = (cle_nom, cle_niveau)" in endpoint
    assert "niveau_exact" in endpoint


def test_sidebar_css_braces_are_balanced():
    css = SIDEBAR_CSS.read_text(encoding="utf-8")
    depth = 0
    for char in css:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "CSS contains an unmatched closing brace"
    assert depth == 0, "CSS contains an unmatched opening brace"
