from app.i18n import traduire_html_interface


def test_interface_uses_complement_dictionary():
    html = "<main><p>Routine terminée aujourd’hui. Bravo pour la régularité — à demain pour la prochaine session.</p></main>"
    translated = traduire_html_interface(html, "en")
    assert "Today's routine is complete." in translated
    assert "Routine terminée" not in translated


def test_interface_translates_ui_attributes():
    html = '<input placeholder="Chercher une réponse" title="Voir le mode d’emploi" aria-label="Ouvrir le menu">'
    translated = traduire_html_interface(html, "en")
    assert 'placeholder="Search for an answer"' in translated
    assert 'title="How it works"' in translated
    assert 'aria-label="Open menu"' in translated


def test_interface_keeps_unknown_dynamic_values():
    html = '<div>Université d’Antananarivo</div><p>Bonjour,</p>'
    translated = traduire_html_interface(html, "en")
    assert "Université d’Antananarivo" in translated
    assert "Hello," in translated
