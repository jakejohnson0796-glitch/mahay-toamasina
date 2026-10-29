from app.force_password_change import chemin_autorise_pendant_changement


def test_changement_mot_de_passe_limite_les_routes_autorisees():
    assert chemin_autorise_pendant_changement("GET", "/securite")
    assert chemin_autorise_pendant_changement("POST", "/securite/mot-de-passe")
    assert chemin_autorise_pendant_changement("POST", "/deconnexion")
    assert chemin_autorise_pendant_changement("GET", "/static/auth.css")
    assert not chemin_autorise_pendant_changement("GET", "/quiz")
    assert not chemin_autorise_pendant_changement("POST", "/admin/inscriptions-institutionnelles/importer")
