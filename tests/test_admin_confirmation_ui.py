from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_confirmation_admin_ne_utilise_plus_les_fenetres_natives():
    script = (ROOT / "app" / "static" / "js" / "admin-confirmation.js").read_text(encoding="utf-8")
    assert "window.prompt(" not in script
    assert "window.alert(" not in script
    assert "await window.demanderConfirmationAdmin()" in script
    assert "X-Admin-Confirmation-Password" in script
    assert "admin_confirmation_password" in script


def test_dialogue_admin_est_accessible_et_protege():
    dialogue = (ROOT / "app" / "static" / "js" / "admin-confirmation-dialog.js").read_text(encoding="utf-8")
    assert 'document.createElement("dialog")' in dialogue
    assert 'dialog.showModal()' in dialogue
    assert 'aria-labelledby' in dialogue
    assert 'aria-describedby' in dialogue
    assert 'autocomplete="current-password"' in dialogue
    assert 'type="password"' in dialogue
    assert 'window.localStorage.setItem' not in dialogue
    assert 'sessionStorage' not in dialogue
    assert "Hetsika fitantanana voaaro" in dialogue


def test_base_charge_le_dialogue_et_son_style_avant_le_script_de_confirmation():
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    lien_dialogue = base.index("admin-confirmation-dialog.js")
    lien_script = base.index("/static/js/admin-confirmation.js")
    assert "admin-confirmation.css" in base
    assert lien_dialogue < lien_script


def test_style_dialogue_est_responsive_et_respecte_reduction_mouvement():
    css = (ROOT / "app" / "static" / "admin-confirmation.css").read_text(encoding="utf-8")
    assert ".admin-confirmation-dialog::backdrop" in css
    assert "@media (max-width: 540px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ".admin-confirmation-dialog__visibility" not in css or ".admin-confirmation-dialog__input button" in css
