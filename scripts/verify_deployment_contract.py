"""Verification statique du contrat de deploiement Render avant release."""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "render.yaml"
DOCKERFILE = ROOT / "Dockerfile"

REQUIRED_RENDER_KEYS = {
    "ENVIRONNEMENT",
    "DATABASE_URL",
    "SESSION_SECRET_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_BUCKET",
}
OPTIONAL_GROUPS = [
    {"LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"},
]

def _env_keys(render: str) -> set[str]:
    return set(re.findall(r"^\s*- key: ([A-Z0-9_]+)\s*$", render, flags=re.MULTILINE))

def verifier_contrat_render() -> tuple[int, int]:
    render = RENDER.read_text(encoding="utf-8")
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    keys = _env_keys(render)
    assert "type: web" in render
    assert "runtime: docker" in render
    assert "healthCheckPath: /health" in render
    assert "value: production" in render
    assert REQUIRED_RENDER_KEYS <= keys, sorted(REQUIRED_RENDER_KEYS - keys)
    for group in OPTIONAL_GROUPS:
        assert group <= keys, sorted(group - keys)
    for key in ("DATABASE_URL", "SESSION_SECRET_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_KEY", "LIVEKIT_API_SECRET"):
        bloc = re.search(rf"(?ms)^\s*- key: {re.escape(key)}\s*$.*?(?=^\s*- key: |\Z)", render)
        assert bloc is not None, key
        assert "sync: false" in bloc.group(0), key
    assert "uvicorn app.main:app --host 0.0.0.0 --port " + "${PORT:-8080}" in dockerfile
    assert "--workers" not in dockerfile
    assert "EXPOSE 8080" in dockerfile
    return len(keys), len(REQUIRED_RENDER_KEYS)

if __name__ == "__main__":
    total, minimum = verifier_contrat_render()
    print(f"[DEPLOYMENT] contrat Render valide: {total} variables declarees, {minimum} obligatoires")
