import pytest

from app import main


def test_etape_initialisation_journalise_la_duree_et_le_statut(monkeypatch, capsys):
    monkeypatch.setattr(main.app.state, "initialisation_etape", "en_attente", raising=False)

    resultat = main._executer_etape_initialisation("test_etape", lambda: "termine")

    assert resultat == "termine"
    assert main.app.state.initialisation_etape == "terminee:test_etape"
    journal = capsys.readouterr().out
    assert "[INIT DATA] Debut etape: test_etape" in journal
    assert "[INIT DATA] Fin etape: test_etape duree=" in journal


def test_etape_initialisation_conserve_le_nom_de_l_etape_en_erreur(monkeypatch, capsys):
    monkeypatch.setattr(main.app.state, "initialisation_etape", "en_attente", raising=False)

    def echouer():
        raise RuntimeError("erreur de test")

    with pytest.raises(RuntimeError, match="erreur de test"):
        main._executer_etape_initialisation("etape_bloquee", echouer)

    assert main.app.state.initialisation_etape == "erreur:etape_bloquee"
    assert "[INIT DATA] Echec etape: etape_bloquee" in capsys.readouterr().out


def test_health_expose_etat_et_etape_initialisation(monkeypatch):
    monkeypatch.setattr(main.app.state, "initialisation_etat", "en_cours", raising=False)
    monkeypatch.setattr(
        main.app.state, "initialisation_etape", "reconciliation_referentiel", raising=False
    )

    resultat = main.health()

    assert resultat["initialisation_etat"] == "en_cours"
    assert resultat["initialisation_etape"] == "reconciliation_referentiel"
