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



def test_classe_salle_verrouille_les_commandes_avant_connexion_livekit():
    source = (ROOT / "app" / "templates" / "classe_salle.html").read_text(encoding="utf-8")
    for identifiant in (
        'id="btn-micro"',
        'id="btn-camera"',
        'id="btn-lever-main"',
        'id="btn-tableau"',
        'id="btn-participants"',
        'id="btn-economie-donnees"',
    ):
        ligne = next(l for l in source.splitlines() if identifiant in l)
        assert "disabled" in ligne
    assert "definirEtatConnexion(false)" in source
    assert "RoomEvent.Reconnecting" in source
    assert "RoomEvent.Reconnected" in source


def test_chat_salle_utilise_le_nom_signe_par_livekit_et_limite_les_messages():
    source = (ROOT / "app" / "templates" / "classe_salle.html").read_text(encoding="utf-8")
    assert 'typeof donnees.texte !== "string"' in source
    assert "texte.length > 500" in source
    assert 'ajouterMessageChat(participant.identity, participant.name || "Participant", texte, false)' in source
