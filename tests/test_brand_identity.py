"""Regression checks for the MITARIDALA brand migration."""

from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
LEGACY_BRAND = "Gasy" + " Mahay"
LEGACY_ALIAS = "Mahay" + " Toamasina"


def test_public_surfaces_do_not_expose_legacy_brand() -> None:
    """Catch old product naming left in a template or launch-facing file."""
    text_extensions = {".py", ".html", ".js", ".css", ".json", ".svg", ".md", ".txt", ".yaml", ".yml"}
    targets = [
        path for path in (ROOT / "app").rglob("*")
        if path.is_file() and path.suffix.casefold() in text_extensions
    ]
    targets.extend(ROOT / relative for relative in (".env.example", "README.md", "render.yaml"))
    leftovers = [
        f"{path.relative_to(ROOT)}"
        for path in targets
        if path.is_file() and any(legacy.casefold() in path.read_text(encoding="utf-8").casefold() for legacy in (LEGACY_BRAND, LEGACY_ALIAS))
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
