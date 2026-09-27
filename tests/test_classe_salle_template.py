from pathlib import Path

from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parents[1]


def test_classe_salle_template_jinja_compile():
    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"))
    template = env.get_template("classe_salle.html")
    assert template is not None


def test_classe_salle_template_conserve_les_blocs_attendus():
    source = (ROOT / "app" / "templates" / "classe_salle.html").read_text(encoding="utf-8")
    assert '{% extends "base.html" %}' in source
    assert '{% block contenu %}' in source
    assert '{% endblock %}' in source
    assert 'id="salle-virtuelle"' in source
    assert 'id="form-chat-salle"' in source
    assert 'livekit-client@2.17.0' in source
