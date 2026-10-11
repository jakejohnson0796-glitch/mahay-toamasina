"""Regression checks for language preference placement and circle hierarchy consistency."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
SIDEBAR_CSS = ROOT / "app" / "static" / "sidebar.css"
CIRCLES_TEMPLATE = ROOT / "app" / "templates" / "cercles_list.html"
CIRCLES_JS = ROOT / "app" / "static" / "js" / "cercles-list.js"
CIRCLES_CSS = ROOT / "app" / "static" / "circle-professional.css"
CIRCLES_ROUTER = ROOT / "app" / "routers" / "cercles_router.py"
ACADEMIC_ROUTER = ROOT / "app" / "routers" / "academique_router.py"
ACADEMIC = ROOT / "app" / "referentiel_academique.py"


def test_language_selector_is_a_single_control_in_the_sidebar_preferences_footer():
    base = BASE.read_text(encoding="utf-8")
    css = SIDEBAR_CSS.read_text(encoding="utf-8")
    assert base.count('id="select-langue"') == 1
    control = base.index('class="tb-sidebar-langue tb-sidebar-langue-footer"')
    assert control < base.index("</aside>")
    assert base.index('class="tb-sidebar-nav"') < control
    assert 'label for="select-langue" data-langue-label' in base
    assert 'option value="fr">Français</option>' in base
    assert 'option value="mg">Malagasy</option>' in base
    assert ".tb-sidebar-langue-footer" in css
    assert "body.sidebar-compact .tb-sidebar-langue" in css
    assert "@media (prefers-reduced-motion:reduce)" in css


def test_circle_ui_uses_human_study_level_labels_but_keeps_normalized_codes():
    template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
    assert '"L1": "Licence 1"' in template
    assert '"M1": "Master 1"' in template
    assert 'value="{{ n }}" data-no-translate' in template
    assert 'niveaux_affichage.get(n, n)' in template
    assert 'niveaux_affichage.get(info.cercle.niveau, info.cercle.niveau)' in template
    assert "Parcours national" in template
    assert "Tronc commun" in template
    assert "Groupe libre" in template
    assert "Référentiel à vérifier" in template
    assert 'class="carte-claire-avatar carte-claire-avatar-couleur-{{ info.cercle.id % 5 }}"' in template
    assert 'style="display:none;"' not in template.split('id="creation-info-tronc-commun"', 1)[1].split("</p>", 1)[0]


def test_circle_creation_offers_explicit_tronc_commun_and_resets_stale_level():
    js = CIRCLES_JS.read_text(encoding="utf-8")
    template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
    assert 'option(parcours, "tronc_commun", "Tronc commun (sans parcours spécifique)", false)' in js
    assert "parcours.required = true" in js
    assert "niveau.value = \"\";\n      niveau.disabled = !mention.value;" in js
    assert 'id="creation-info-tronc-commun" hidden' in template
    assert "infoTronc.hidden = false" in js
    assert "si aucun parcours spécifique n'est proposé" in js


def test_server_does_not_silently_convert_incomplete_academic_choices_to_free_groups():
    router = CIRCLES_ROUTER.read_text(encoding="utf-8")
    template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
    assert 'erreur=niveau_requis' in router
    assert 'erreur=mention_requise' in router
    assert 'parcours_mention_incoherente' in router
    assert 'request.query_params.get("erreur") == "niveau_requis"' in template
    assert 'request.query_params.get("erreur") == "mention_requise"' in template
    assert 'filiere_id_nettoye = None if filiere_id in (None, "", "tronc_commun")' in router
    assert 'mention_id_nettoye != filiere.mention_id' in router


def test_circle_type_and_pathway_api_validate_effective_mention_and_requested_level():
    academic = ACADEMIC.read_text(encoding="utf-8")
    api = ACADEMIC_ROUTER.read_text(encoding="utf-8")
    assert 'def type_cercle(cercle: CercleEtude, session: Optional[Session] = None)' in academic
    assert 'filiere.mention_id != mention_effective_id' in academic
    assert 'filiere.niveau != cercle.niveau' in academic
    assert 'mention_cercle_effective = func.coalesce(' in academic
    assert 'filiere_reference.niveau != niveau' in academic
    assert 'Faculte.universite_id == ProgrammeUniversitaire.universite_id' in api
    assert 'explicites or [f for f in candidats if f.niveau is None]' in api
    assert 'if niveau and niveau not in NIVEAUX' in api


def test_circle_style_layer_is_loaded_and_keeps_hierarchy_labels_responsive():
    base = BASE.read_text(encoding="utf-8")
    css = CIRCLES_CSS.read_text(encoding="utf-8")
    assert base.count('/static/circle-professional.css?v={{ version_asset(\'circle-professional.css\') }}') == 1
    assert '{% if request.url.path.startswith("/cercles") %}' in base
    assert ".carte-claire-hierarchie" in css
    assert ".puce-niveau" in css
    assert "@media (max-width: 680px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    depth = 0
    for char in css:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0, "CSS has an unmatched closing brace"
    assert depth == 0, "CSS has an unmatched opening brace"
