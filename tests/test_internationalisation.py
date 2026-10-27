from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_selecteur_de_langue_est_dans_les_parametres_et_le_script_est_global():
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    settings = (ROOT / "app" / "templates" / "securite.html").read_text(encoding="utf-8")
    assert "select-langue" not in base
    assert 'id="select-langue-parametres"' in settings
    assert '<option value="fr" data-no-translate>Français</option>' in settings
    assert '<option value="mg" data-no-translate>Malagasy</option>' in settings
    assert '<option value="en" data-no-translate>English</option>' in settings
    assert 'src="/static/js/langue.js?' in base
    assert 'lang="fr"' in base


def test_traduction_ne_depend_d_aucun_service_tiers_et_protege_le_contenu_ia():
    js = (ROOT / "app" / "static" / "js" / "langue.js").read_text(encoding="utf-8")
    assert 'localStorage' in js
    assert '"mahay-langue"' in js
    assert '"[data-rendu]"' in js
    assert '".ai-rendered-content"' in js
    assert "TRADUCTIONS_MG" in js
    assert "fetch(" not in js
    assert "XMLHttpRequest" not in js


def test_styles_du_selecteur_sont_responsifs_et_accessibles_dans_les_parametres():
    css = (ROOT / "app" / "static" / "interface-polish.css").read_text(encoding="utf-8")
    sidebar_css = (ROOT / "app" / "static" / "sidebar.css").read_text(encoding="utf-8")
    assert ".ops-language-settings" in css
    assert ".ops-language-settings select:focus-visible" in css
    assert "@media (max-width: 640px)" in css
    assert ".tb-sidebar-langue" not in sidebar_css


def test_ci_lance_le_test_navigateur_du_selecteur_de_langue():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "node scripts/smoke_language_switcher.mjs" in workflow



def test_traductions_des_libelles_signales_et_des_etats_dynamiques():
    js = (ROOT / "app" / "static" / "js" / "langue.js").read_text(encoding="utf-8")
    cles = (
        "Illustrations d’étude intégrées localement dans MITARIDALA : aucune dépendance à un service d’images externe.",
        "Génération…",
        "Validation…",
        "Préparation…",
        "Recherche…",
        "Rechercher dans l'historique",
        "Catégories d'emojis",
        "Partager l'écran",
        "QR code d'activation",
        "Parcours d'apprentissage",
        "Mission d'apprentissage",
    )
    for cle in cles:
        assert f'"{cle}":' in js, f"Traduction manquante : {cle}"

    assert r'cle.match(/^(\d+)\s*\/\s*(\d+)\s+répondues?$/i)' in js
    assert r'cle.match(/^Aller à la question\s+(\d+)$/i)' in js


def test_options_academiques_creees_en_javascript_sont_protegees():
    cascade = (ROOT / "app" / "static" / "js" / "cascade-academique.js").read_text(encoding="utf-8")
    cercles = (ROOT / "app" / "static" / "js" / "cercles-list.js").read_text(encoding="utf-8")
    assert 'option.setAttribute("data-no-translate", "")' in cascade
    assert 'ajouterOption(composante, row.id, row.nom, String(row.id) === String(valeur || ""), true)' in cascade
    assert 'ajouterOption(mention, row.id, row.nom, String(row.id) === String(valeur || ""), true)' in cascade
    assert 'ajouterOption(filiere, row.id, label, String(row.id) === String(courant.filiere || ""), true)' in cascade
    assert 'node.setAttribute("data-no-translate", "")' in cercles
    assert 'option(select, item.id, item.nom, String(item.id) === valeur, true)' in cercles


def test_confirmations_administrateur_sont_bilingues_hors_du_dom():
    js = (ROOT / "app" / "static" / "js" / "admin-confirmation.js").read_text(encoding="utf-8")
    assert "function texteSelonLangue(francais, malagasy)" in js
    assert "Hetsika fitantanana voaaro" in js
    assert "Nolavina ny fanamafisan’ny mpitantana." in js
