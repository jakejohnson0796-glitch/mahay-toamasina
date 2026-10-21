from app.templating import templates


def test_fiche_deja_validee_ne_reaffiche_pas_le_formulaire_de_validation():
    source = templates.env.loader.get_source(templates.env, "document_parcours.html")[0]

    # Une fiche déjà validée doit afficher l'état et le bouton quiz,
    # pas demander une deuxième validation à son propriétaire.
    assert '{% if peut_valider_fiche and not fiche_validee %}' in source
    assert '{% if fiche_validee %}Fiche pédagogique validée{% else %}' in source
    assert "Lancer le Quiz IA maintenant" in source


def test_statut_du_carnet_ia_est_distinct_de_la_validation_pedagogique():
    source = templates.env.loader.get_source(templates.env, "document_parcours.html")[0]

    assert 'fiche_revision_document.statut.value == "en_attente"' in source
    assert 'fiche_revision_document.statut.value == "en_cours"' in source
    assert "La génération du carnet est indépendante de la vérification pédagogique" in source
    assert "Actualiser l’état de la fiche" in source


def test_parcours_document_compile():
    assert templates.env.get_template("document_parcours.html") is not None
