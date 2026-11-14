from types import SimpleNamespace

import pytest

from app.config import parametres
from app.websocket_security import origine_websocket_autorisee


def _websocket(origin, host="mitaridala.onrender.com"):
    return SimpleNamespace(headers={"origin": origin, "host": host})


def test_websocket_origin_accepts_exact_https_host_in_production(monkeypatch):
    monkeypatch.setattr(parametres, "environnement", "production")
    assert origine_websocket_autorisee(
        _websocket("https://mitaridala.onrender.com")
    ) is True


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "null",
        "http://mitaridala.onrender.com",
        "https://attaquant.example",
        "https://mitaridala.onrender.com.attacker.example",
        "https://user@mitaridala.onrender.com",
        "https://mitaridala.onrender.com/path",
        "https://mitaridala.onrender.com/?x=1",
        "https://mitaridala.onrender.com/#fragment",
        "https://mitaridala.onrender.com:port",
        "javascript://mitaridala.onrender.com",
    ],
)
def test_websocket_origin_rejects_missing_forged_or_malformed_origin(monkeypatch, origin):
    monkeypatch.setattr(parametres, "environnement", "production")
    assert origine_websocket_autorisee(_websocket(origin)) is False


def test_websocket_origin_requires_host_header(monkeypatch):
    monkeypatch.setattr(parametres, "environnement", "production")
    assert origine_websocket_autorisee(
        SimpleNamespace(headers={"origin": "https://mitaridala.onrender.com", "host": ""})
    ) is False


def test_websocket_origin_allows_matching_http_origin_only_in_development(monkeypatch):
    monkeypatch.setattr(parametres, "environnement", "developpement")
    assert origine_websocket_autorisee(
        _websocket("http://localhost:8000", "localhost:8000")
    ) is True
    monkeypatch.setattr(parametres, "environnement", "production")
    assert origine_websocket_autorisee(
        _websocket("http://localhost:8000", "localhost:8000")
    ) is False


def test_websocket_origin_comparison_includes_port(monkeypatch):
    monkeypatch.setattr(parametres, "environnement", "developpement")
    assert origine_websocket_autorisee(
        _websocket("http://localhost:8001", "localhost:8000")
    ) is False


def test_circle_and_class_websockets_share_the_origin_guard():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    circles = (root / "app/routers/cercles_router.py").read_text(encoding="utf-8")
    classes = (root / "app/routers/classe_router.py").read_text(encoding="utf-8")

    assert "from ..websocket_security import origine_websocket_autorisee" in circles
    assert "if not origine_websocket_autorisee(websocket):" in circles
    assert "from ..websocket_security import origine_websocket_autorisee" in classes
    assert "if not origine_websocket_autorisee(websocket):" in classes
