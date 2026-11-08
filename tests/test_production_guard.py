from dataclasses import replace

import pytest

from app.config import Parametres
from app.production_guard import erreurs_configuration_production, valider_configuration_production
from app.security_headers import _construire_csp


def _production_complete() -> Parametres:
    return Parametres(
        environnement="production",
        session_secret_key="x" * 64,
        database_url="postgresql://mahay_runtime.ref-test:secret@example.test:5432/mahay",
        migration_database_url="postgresql://postgres.ref-test:secret@example.test:5432/mahay",
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


def test_configuration_production_refuse_un_compte_runtime_privilegie() -> None:
    config = replace(
        _production_complete(),
        database_url="postgresql://postgres.ref-test:secret@example.test:5432/mahay",
    )
    erreurs = erreurs_configuration_production(config)
    assert any("rôle personnalisé mahay_runtime" in erreur for erreur in erreurs)
    assert any("BYPASSRLS" in erreur and "contrôlés séparément" in erreur for erreur in erreurs)


def test_configuration_production_exige_exactement_mahay_runtime() -> None:
    config = replace(
        _production_complete(),
        database_url="postgresql://app_user.ref-test:secret@example.test:5432/mahay",
    )
    erreurs = erreurs_configuration_production(config)
    assert any("exactement le rôle personnalisé mahay_runtime" in erreur for erreur in erreurs)


def test_configuration_production_refuse_le_meme_role_pour_runtime_et_migrations() -> None:
    config = replace(
        _production_complete(),
        migration_database_url="postgresql://mahay_runtime.ref-test:other@example.test:5432/mahay",
    )
    erreurs = erreurs_configuration_production(config)
    assert any("deux rôles PostgreSQL distincts" in erreur for erreur in erreurs)


def test_configuration_production_exige_un_compte_migrations_separe() -> None:
    config = replace(_production_complete(), migration_database_url="")
    erreurs = erreurs_configuration_production(config)
    assert any("MIGRATION_DATABASE_URL" in erreur for erreur in erreurs)


def test_configuration_production_refuse_stockage_ephemere() -> None:
    config = replace(_production_complete(), supabase_url="", supabase_service_key="")
    erreurs = erreurs_configuration_production(config)
    assert any("SUPABASE_URL" in erreur for erreur in erreurs)


def test_configuration_livekit_doit_etre_complete() -> None:
    config = replace(_production_complete(), livekit_url="wss://livekit.example")
    erreurs = erreurs_configuration_production(config)
    assert any("LIVEKIT_URL" in erreur for erreur in erreurs)


def test_csp_production_n_utilise_pas_unsafe_inline_hors_style_attr() -> None:
    csp = _construire_csp("nonce-test")
    # MODIF : la directive autorise explicitement unsafe-inline uniquement
    # pour style-src-attr, car KaTeX génère des attributs style.
    script_src = csp.split("script-src ", 1)[1].split(";", 1)[0]
    style_src = csp.split("style-src ", 1)[1].split(";", 1)[0]
    style_attr = csp.split("style-src-attr ", 1)[1].split(";", 1)[0]
    assert "'unsafe-inline'" not in script_src
    assert "'unsafe-inline'" not in style_src
    assert "'unsafe-inline'" in style_attr
    assert "https://cdn.jsdelivr.net" in style_src
    assert "script-src-attr 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert "'nonce-nonce-test'" in csp


def test_configuration_production_refuse_une_release_non_identifiee() -> None:
    config = replace(_production_complete(), release_commit="unknown")
    erreurs = erreurs_configuration_production(config)
    assert any("release" in erreur.lower() for erreur in erreurs)


def test_render_est_par_defaut_en_production_si_variable_absente(monkeypatch) -> None:
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("ENVIRONNEMENT", raising=False)
    config = Parametres()
    assert config.environnement == "production"


def test_mode_developpement_local_reste_disponible_sans_render(monkeypatch) -> None:
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("ENVIRONNEMENT", raising=False)
    config = Parametres()
    assert config.environnement == "developpement"


@pytest.mark.parametrize("pilote", ["psycopg", "psycopg2"])
def test_configuration_production_accepte_les_uri_postgresql_avec_pilote(pilote):
    config = replace(
        _production_complete(),
        database_url=f"postgresql+{pilote}://mahay_runtime.ref-test:secret@example.test:5432/mahay",
        migration_database_url=f"postgresql+{pilote}://postgres.ref-test:secret@example.test:5432/mahay",
    )
    assert erreurs_configuration_production(config) == []


def test_configuration_production_refuse_une_uri_base_malformee():
    config = replace(_production_complete(), database_url="postgresql+://")
    erreurs = erreurs_configuration_production(config)
    assert any("DATABASE_URL" in erreur for erreur in erreurs)
