"""Regression checks for the MITARIDALA brand migration."""

from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
LEGACY_BRAND = "Gasy" + " Mahay"


def test_public_surfaces_do_not_expose_legacy_brand() -> None:
    """Catch old product naming left in a template or launch-facing file."""
    targets = list((ROOT / "app" / "templates").rglob("*.html"))
    targets.extend(
        ROOT / relative
        for relative in (
            "app/main.py",
            "app/config.py",
            "app/email_utils.py",
            "app/routers/auth_router.py",
            "app/static/manifest.json",
            ".env.example",
            "README.md",
            "render.yaml",
        )
    )
    leftovers = [
        f"{path.relative_to(ROOT)}"
        for path in targets
        if path.is_file() and LEGACY_BRAND.casefold() in path.read_text(encoding="utf-8").casefold()
    ]
    assert not leftovers, "Ancienne marque encore visible dans : " + ", ".join(sorted(leftovers))


def test_mitaridala_brand_assets_and_pwa_metadata_exist() -> None:
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    logo = ROOT / "app" / "static" / "images" / "site" / "mitaridala-mark.svg"
    manifest = json.loads((ROOT / "app" / "static" / "manifest.json").read_text(encoding="utf-8"))

    assert "MITARIDALA" in base
    assert "mitaridala-mark.svg" in base
    assert logo.is_file()
    assert manifest.get("short_name") == "MITARIDALA"
    assert "MITARIDALA" in manifest.get("name", "")
