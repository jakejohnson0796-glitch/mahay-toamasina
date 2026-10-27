from types import SimpleNamespace

from app.client_ip import adresse_ip_client


def _request(remote="10.0.0.5", headers=None):
    return SimpleNamespace(
        client=SimpleNamespace(host=remote),
        headers=headers or {},
    )


def test_local_request_does_not_trust_spoofable_forwarded_headers(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    request = _request(headers={
        "cf-ray": "ray-test",
        "cf-connecting-ip": "203.0.113.10",
        "x-forwarded-for": "203.0.113.11",
    })
    assert adresse_ip_client(request) == "10.0.0.5"


def test_render_request_uses_validated_cloudflare_client_ip(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    request = _request(headers={
        "cf-ray": "ray-test",
        "cf-connecting-ip": "203.0.113.25",
        "x-forwarded-for": "198.51.100.4, 203.0.113.25",
    })
    assert adresse_ip_client(request) == "203.0.113.25"


def test_invalid_cloudflare_ip_falls_back_to_rightmost_valid_forwarded_ip(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    request = _request(headers={
        "cf-ray": "ray-test",
        "cf-connecting-ip": "not-an-ip",
        "x-forwarded-for": "203.0.113.1, 198.51.100.40",
    })
    assert adresse_ip_client(request) == "198.51.100.40"


def test_malformed_forwarded_headers_fall_back_to_socket_ip(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    request = _request(remote="10.0.0.8", headers={
        "cf-ray": "ray-test",
        "cf-connecting-ip": "not-an-ip",
        "x-forwarded-for": "unknown, invalid",
    })
    assert adresse_ip_client(request) == "10.0.0.8"
