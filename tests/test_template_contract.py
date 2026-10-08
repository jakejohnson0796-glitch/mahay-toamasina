from app.templating import templates


def test_mes_revisions_template_compile():
    template = templates.env.get_template("mes_revisions.html")
    assert template is not None


def test_quiz_templates_compile():
    for name in ("quiz_passer.html", "quiz_resultat.html"):
        template = templates.env.get_template(name)
        assert template is not None
