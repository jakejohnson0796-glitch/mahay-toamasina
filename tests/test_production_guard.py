from dataclasses import replace

import pytest

from app.config import Parametres
from app.production_guard import erreurs_configuration_production, valider_configuration_production
from app.security_headers import _construire_csp


def _production_complete() -> Parametres:
    return Parametres(
        environnement="production",
        session_secret_key="x" * 64,
        database_url="postgresql://postgres:secret@example.test:5432/mahay",
        supabase_url="https://example.supabase.co",
        supabase_service_key="service-secret",
    )


def test_configuration_production_complete_est_acceptee() -> None:
    config = _production_complete()
    assert erreurs_configuration_production(config) == []
    valider_configuration_production(config)


def test_configuration_production_refuse_sqlite_et_secret_faible() -> None:
    config = replace(
        _production_complete(),
        database_url="sqlite:///./mahay.db",
        session_secret_key="court",
    )
    erreurs = erreurs_configuration_production(config)
    assert any("DATABASE_URL" in erreur for erreur in erreurs)
    assert any("SESSION_SECRET_KEY" in erreur for erreur in erreurs)
    with pytest.raises(RuntimeError, match="Configuration production incomplete"):
        valider_configuration_production(config)


def test_configuration_production_refuse_stockage_ephemere() -> None:
    config = replace(_production_complete(), supabase_url="", supabase_service_key="")
    erreurs = erreurs_configuration_production(config)
    assert any("SUPABASE_URL" in erreur for erreur in erreurs)


def test_configuration_livekit_doit_etre_complete() -> None:
    config = replace(_production_complete(), livekit_url="wss://livekit.example")
    erreurs = erreurs_configuration_production(config)
    assert any("LIVEKIT_URL" in erreur for erreur in erreurs)


def test_csp_production_n_utilise_pas_unsafe_inline() -> None:
    csp = _construire_csp("nonce-test")
    assert "'unsafe-inline'" not in csp
    assert "script-src-attr 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert "'nonce-nonce-test'" in csp
