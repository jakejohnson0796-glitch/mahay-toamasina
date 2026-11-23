"""Regressions contre les fuites de configuration et de secrets."""
from __future__ import annotations

import os
import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_env_example_keeps_credential_values_empty() -> None:
    """Les exemples ne doivent contenir aucune vraie valeur d'identifiant."""
    sensitive_keys = {
        "DATABASE_URL",
        "REDIS_URL",
        "SESSION_SECRET_KEY",
        "SUPABASE_SERVICE_KEY",
        "GROQ_API_KEY",
        "GEMINI_API_KEY",
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
        "BREVO_API_KEY",
        "ADMIN_INITIAL_PASSWORD",
        "SMTP_UTILISATEUR",
        "SMTP_MOT_DE_PASSE",
    }
    values: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key.strip() in sensitive_keys:
            values[key.strip()] = value.strip()

    assert values.keys() >= sensitive_keys
    assert all(value == "" for value in values.values()), {
        key: "valeur non vide dans .env.example"
        for key, value in values.items()
        if value
    }


def test_session_secret_has_no_weak_implicit_default(monkeypatch) -> None:
    monkeypatch.delenv("SESSION_SECRET_KEY", raising=False)
    from app.config import Parametres

    assert Parametres().session_secret_key == ""


def test_environment_diagnostic_never_prints_secret_values(monkeypatch, capsys) -> None:
    import dotenv

    monkeypatch.setattr(dotenv, "find_dotenv", lambda usecwd=True: "")
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: True)
    sentinels = {
        "DATABASE_URL": "postgresql://private-user:private-password@db.example.test/app",
        "SUPABASE_URL": "https://private-project.example.test",
        "GROQ_API_KEY": "gsk_PRIVATE_TEST_VALUE_123456",
    }
    for key, value in sentinels.items():
        monkeypatch.setenv(key, value)

    runpy.run_path(str(ROOT / "verif"))
    output = capsys.readouterr().out

    for value in sentinels.values():
        assert value not in output
    assert "DATABASE_URL configurée : oui" in output
    assert "SUPABASE_URL configurée : oui" in output
    assert "GROQ_API_KEY configurée : oui" in output
    assert str(ROOT) not in output
