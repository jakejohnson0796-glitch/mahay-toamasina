from app.templating import templates


def test_mes_revisions_template_compile():
    template = templates.env.get_template("mes_revisions.html")
    assert template is not None
