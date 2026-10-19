#!/usr/bin/env python3
"""Download pinned browser libraries into app/static/vendor during Docker/CI builds.

Every npm archive is checked against the registry's published SHA-512 SRI value
before extraction. No application request has to download these libraries from a CDN.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import shutil
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "app" / "static" / "vendor"
USER_AGENT = "MahayToamasina-FrontendVendor/1.0"
TIMEOUT_SECONDS = 60

PACKAGES: dict[str, dict[str, Any]] = {
    "katex": {
        "version": "0.19.0",
        "target": "katex",
        "license_label": "MIT",
        "files": [
            ("dist/katex.min.js", "katex.min.js"),
            ("dist/katex.min.css", "katex.min.css"),
            ("dist/contrib/mhchem.min.js", "contrib/mhchem.min.js"),
        ],
        "font_prefix": "dist/fonts/",
        "font_extensions": {".woff2", ".woff", ".ttf"},
        "license_candidates": ["LICENSE", "LICENSE.md", "LICENSE.txt"],
    },
    "marked": {
        "version": "18.1.1",
        "target": "marked",
        "license_label": "MIT",
        "files_candidates": [
            (["marked.min.js", "lib/marked.umd.js", "lib/marked.umd.min.js"], "marked.min.js"),
        ],
        "license_candidates": ["LICENSE.md", "LICENSE", "LICENSE.txt"],
    },
    "dompurify": {
        "version": "3.4.17",
        "target": "dompurify",
        "license_label": "MPL-2.0 OR Apache-2.0",
        "files": [("dist/purify.min.js", "purify.min.js")],
        "license_candidates": ["LICENSE", "LICENSE.md", "LICENSE.txt"],
    },
    "@highlightjs/cdn-assets": {
        "version": "11.12.0",
        "target": "highlightjs",
        "license_label": "BSD-3-Clause",
        "files_candidates": [(["highlight.min.js", "build/highlight.min.js"], "highlight.min.js")],
        "license_candidates": ["LICENSE", "LICENSE.md", "LICENSE.txt"],
    },
}


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return response.read()


def fetch_verified_package(package_name: str, version: str) -> tuple[dict[str, Any], dict[str, bytes]]:
    encoded_name = urllib.parse.quote(package_name, safe="")
    metadata_url = f"https://registry.npmjs.org/{encoded_name}/{version}"
    try:
        metadata = json.loads(fetch_bytes(metadata_url).decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Impossible de lire les métadonnées npm de {package_name}@{version}: {exc}") from exc

    if metadata.get("name") != package_name or metadata.get("version") != version:
        raise RuntimeError(f"Le registre n'a pas retourné la version épinglée {package_name}@{version}.")

    dist = metadata.get("dist") or {}
    tarball_url = dist.get("tarball", "")
    integrity = dist.get("integrity", "")
    if urlparse(tarball_url).hostname != "registry.npmjs.org":
        raise RuntimeError(f"URL de tarball npm inattendue pour {package_name}@{version}: {tarball_url}")
    if not integrity.startswith("sha512-"):
        raise RuntimeError(f"Empreinte SHA-512 SRI absente pour {package_name}@{version}.")

    try:
        archive_bytes = fetch_bytes(tarball_url)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Impossible de télécharger {package_name}@{version}: {exc}") from exc

    actual_integrity = "sha512-" + base64.b64encode(hashlib.sha512(archive_bytes).digest()).decode("ascii")
    if actual_integrity != integrity:
        raise RuntimeError(f"Échec de vérification d'intégrité du paquet {package_name}@{version}.")

    files: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile() or not member.name.startswith("package/"):
                    continue
                relative = member.name[len("package/"):]
                if relative.startswith("/") or ".." in Path(relative).parts:
                    raise RuntimeError(f"Chemin interdit dans le tarball {package_name}: {relative}")
                extracted = archive.extractfile(member)
                if extracted is not None:
                    files[relative] = extracted.read()
    except (tarfile.TarError, OSError) as exc:
        raise RuntimeError(f"Archive npm invalide pour {package_name}@{version}: {exc}") from exc

    return metadata, files


def require_file(files: dict[str, bytes], candidates: list[str], package_name: str) -> tuple[str, bytes]:
    for candidate in candidates:
        if candidate in files:
            return candidate, files[candidate]
    raise RuntimeError(
        f"Fichier navigateur manquant dans {package_name}@{PACKAGES[package_name]['version']}: "
        + ", ".join(candidates)
    )


def write_asset(relative_path: str, data: bytes, manifest_files: dict[str, str]) -> None:
    destination = VENDOR / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    manifest_files[relative_path] = hashlib.sha256(data).hexdigest()


def main() -> None:
    VENDOR.mkdir(parents=True, exist_ok=True)
    for folder in ("katex", "marked", "dompurify", "highlightjs", "licenses"):
        destination = VENDOR / folder
        if destination.exists():
            shutil.rmtree(destination)

    manifest: dict[str, Any] = {
        "generated_by": "scripts/vendor_frontend_dependencies.py",
        "registry": "https://registry.npmjs.org/",
        "packages": {},
    }
    notice_lines = [
        "# Notices des bibliothèques JavaScript tierces",
        "",
        "Les fichiers sont téléchargés pendant la construction de l'image et servis localement.",
        "Les archives sont vérifiées avec leur empreinte SHA-512 SRI publiée par le registre npm.",
        "",
    ]

    for package_name, spec in PACKAGES.items():
        version = spec["version"]
        print(f"Téléchargement et vérification de {package_name}@{version}...", flush=True)
        metadata, files = fetch_verified_package(package_name, version)
        target = spec["target"]
        published_license = metadata.get("license")
        if isinstance(published_license, dict):
            published_license = published_license.get("type", spec["license_label"])
        if not published_license:
            published_license = spec["license_label"]

        package_manifest_files: dict[str, str] = {}
        package_asset_paths: list[str] = []
        for source, destination in spec.get("files", []):
            if source not in files:
                raise RuntimeError(f"Fichier navigateur manquant dans {package_name}@{version}: {source}")
            relative = f"{target}/{destination}"
            write_asset(relative, files[source], package_manifest_files)
            package_asset_paths.append(relative)

        for candidates, destination in spec.get("files_candidates", []):
            source, data = require_file(files, candidates, package_name)
            relative = f"{target}/{destination}"
            write_asset(relative, data, package_manifest_files)
            package_asset_paths.append(relative)

        font_prefix = spec.get("font_prefix")
        if font_prefix:
            font_items = sorted(
                (name, data)
                for name, data in files.items()
                if name.startswith(font_prefix) and Path(name).suffix.lower() in spec["font_extensions"]
            )
            if not any(name.endswith(".woff2") for name, _ in font_items):
                raise RuntimeError(f"Les polices WOFF2 de KaTeX sont absentes de {package_name}@{version}.")
            for source, data in font_items:
                relative = f"{target}/fonts/{source[len(font_prefix):]}"
                write_asset(relative, data, package_manifest_files)
                package_asset_paths.append(relative)

        _, license_bytes = require_file(files, spec["license_candidates"], package_name)
        license_name = f"licenses/{target}-LICENSE.txt"
        write_asset(license_name, license_bytes, package_manifest_files)

        manifest["packages"][package_name] = {
            "version": version,
            "license": published_license,
            "registry_integrity": metadata["dist"]["integrity"],
            "tarball_url": metadata["dist"]["tarball"],
            "assets": package_asset_paths,
            "license_file": license_name,
            "sha256": package_manifest_files,
        }
        notice_lines.extend([
            f"## {package_name} {version}",
            "",
            f"- Licence déclarée : {published_license}",
            f"- Métadonnées : https://www.npmjs.com/package/{package_name}/v/{version}",
            f"- Texte de licence embarqué : {license_name}",
            "",
        ])

    (VENDOR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (VENDOR / "THIRD_PARTY_NOTICES.md").write_text("\n".join(notice_lines), encoding="utf-8")
    count = sum(len(item["sha256"]) - 1 for item in manifest["packages"].values())
    print(f"Paquets locaux installés : {len(PACKAGES)} ; assets vérifiés : {count}.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(f"[frontend-vendor] ERREUR : {exc}") from exc
