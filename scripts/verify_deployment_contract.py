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
    "MIGRATION_DATABASE_URL",
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

def _service_block(render: str, name: str) -> str:
    """Retourne le bloc d'un service web Render sans accéder aux valeurs secrètes."""
    lines = render.splitlines()
    for index, line in enumerate(lines):
        if line == "  - type: web":
            end = next(
                (position for position in range(index + 1, len(lines))
                 if lines[position].startswith("  - type: ")),
                len(lines),
            )
            block = "\\n".join(lines[index:end])
            if re.search(rf"(?m)^    name: {re.escape(name)}$", block):
                return block
    raise AssertionError(f"Service Render absent: {name}")


def verifier_contrat_render() -> tuple[int, int]:
    render = RENDER.read_text(encoding="utf-8")
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    keys = _env_keys(render)
    assert "type: web" in render
    assert "runtime: docker" in render
    assert "healthCheckPath: /health" in render
    assert "value: production" in render
    assert REQUIRED_RENDER_KEYS <= keys, sorted(REQUIRED_RENDER_KEYS - keys)
    # Contrôle service par service : les deux URL doivent être déclarées.
    # sync: false ne remplace pas les valeurs déjà enregistrées sur les services existants.
    for service_name in ("mahay-toamasina", "mitaridala"):
        service_block = _service_block(render, service_name)
        service_keys = _env_keys(service_block)
        required_db_keys = {"DATABASE_URL", "MIGRATION_DATABASE_URL"}
        assert required_db_keys <= service_keys, (
            service_name,
            sorted(required_db_keys - service_keys),
        )
        for key in required_db_keys:
            variable = re.search(
                rf"(?ms)^\\s*- key: {re.escape(key)}\\s*$.*?(?=^\\s*- key: |\\Z)",
                service_block,
            )
            assert variable is not None and "sync: false" in variable.group(0), (
                service_name,
                key,
            )
    for group in OPTIONAL_GROUPS:
        assert group <= keys, sorted(group - keys)
    for key in ("DATABASE_URL", "MIGRATION_DATABASE_URL", "SESSION_SECRET_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_KEY", "LIVEKIT_API_SECRET"):
        bloc = re.search(rf"(?ms)^\s*- key: {re.escape(key)}\s*$.*?(?=^\s*- key: |\Z)", render)
        assert bloc is not None, key
        assert "sync: false" in bloc.group(0), key
    assert "uvicorn app.main:app --host 0.0.0.0 --port " + "${PORT:-8080}" in dockerfile
    commande = dockerfile.split("CMD", 1)[1] if "CMD" in dockerfile else ""
    assert "--workers" not in commande
    assert "EXPOSE 8080" in dockerfile
    return len(keys), len(REQUIRED_RENDER_KEYS)

if __name__ == "__main__":
    total, minimum = verifier_contrat_render()
    print(f"[DEPLOYMENT] contrat Render valide: {total} variables declarees, {minimum} obligatoires")
