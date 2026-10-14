"""Regression checks for the circles chat responsive UX."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "app" / "templates" / "cercle_chat.html").read_text(encoding="utf-8")
ROUTER = (ROOT / "app" / "routers" / "cercles_router.py").read_text(encoding="utf-8")


def test_circle_header_only_displays_real_academic_metadata():
    assert '"mention_cercle": mention_cercle' in ROUTER
    assert '"filiere_cercle": filiere_cercle' in ROUTER
    assert '"niveau_cercle_libelle": niveau_cercle_libelle' in ROUTER
    assert "{% if mention_cercle or filiere_cercle or niveau_cercle_libelle %}" in TEMPLATE
    assert 'aria-label="Informations académiques du cercle"' in TEMPLATE
    assert "Groupe libre" in TEMPLATE


def test_mobile_composer_keeps_file_fallback_and_touch_targets():
    assert ".contenu-clair .barre-composition #form-fichier>.bouton-envoyer-fichier{display:inline-flex!important" in TEMPLATE
    assert "grid-template-columns:44px 44px minmax(0,1fr) 44px!important" in TEMPLATE
    assert ".contenu-clair .barre-composition .bouton-envoyer-message" in TEMPLATE
    assert 'aria-label="Partager un PDF"' in TEMPLATE


def test_empty_chat_uses_compact_height_on_mobile():
    assert ".contenu-clair .fenetre-chat-vide{height:auto!important;min-height:0!important;max-height:none!important" in TEMPLATE
    assert ".contenu-clair .etat-vide-chat-actions{grid-template-columns:1fr" in TEMPLATE


def test_focus_mode_keeps_a_visible_exit_control():
    assert ".cercle-mode-focus .contenu-clair .cercle-chat-outils #bouton-focus-cercle{display:inline-flex!important" in TEMPLATE
    assert 'id="bouton-focus-cercle" title="Activer le mode Focus" aria-label="Mode Focus" aria-pressed="false"' in TEMPLATE


def test_new_messages_do_not_force_scroll_when_reading_history():
    assert "const suivreNouveauxMessages =" in TEMPLATE
    assert "if (suivreNouveauxMessages) fenetreChat.scrollTop = fenetreChat.scrollHeight;" in TEMPLATE


def test_core_chat_features_remain_wired():
    for marker in (
        "new WebSocket(urlWebSocket)",
        "attacherAutocompletionMentions",
        "bouton-emoji-toggle",
        'id="form-fichier"',
        'id="form-reponse-thread"',
        "envoyerReaction",
        "panneau-profil-utilisateur",
        "requestFullscreen()",
        "visibilitychange",
        "mettreAJourPresence",
    ):
        assert marker in TEMPLATE, f"Expected existing circle feature marker: {marker}"
