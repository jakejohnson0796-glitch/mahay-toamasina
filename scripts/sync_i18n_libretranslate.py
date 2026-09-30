#!/usr/bin/env python3
"""Synchronise les chaînes UI manquantes avec LibreTranslate.

Usage:
  LIBRETRANSLATE_URL=http://localhost:5000 \
    python scripts/sync_i18n_libretranslate.py --targets en,mg --write

Le script :
1. parcourt app/templates/*.html ;
2. extrait uniquement les textes HTML et attributs UI littéraux ;
3. ignore les blocs Jinja dynamiques contenant {{...}} ou {%...%} ;
4. conserve toutes les traductions manuelles existantes ;
5. demande à LibreTranslate uniquement les chaînes manquantes ;
6. écrit le résultat dans app/i18n_generated.py.

Aucun appel réseau n'est effectué par l'application pendant l'affichage des pages.
"""
from __future__ import annotations

import argparse
import html
import re
from pathlib import Path
from pprint import pformat

from app.i18n import (
    TRADUCTIONS,
    TRADUCTIONS_UI,
    TRADUCTIONS_UI_COMPLEMENT,
)
from app.libretranslate import (
    LibreTranslateError,
    supported_languages,
    translate_text,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app" / "templates"
GENERATED = ROOT / "app" / "i18n_generated.py"

SKIP_BLOCKS = re.compile(r"<(script|style|pre|code)\b[^>]*>.*?</\1\s*>", re.I | re.S)
TEXT_NODE = re.compile(r">([^<>]+)<")
UI_ATTR = re.compile(
    r'\b(placeholder|title|aria-label|aria-description|data-tooltip)=(["\'])(.*?)\2',
    re.I | re.S,
)
BLOCK_TITLE = re.compile(r"{%\s*block\s+[^%]+%}([^<{]+?){%\s*endblock\s*%}", re.I | re.S)


def _normalise(value: str) -> str:
    value = html.unescape(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def _is_static(value: str) -> bool:
    if not value:
        return False
    if "{{" in value or "}}" in value or "{%" in value or "%}" in value:
        return False
    if value.startswith("http://") or value.startswith("https://"):
        return False
    return not re.fullmatch(r"[-—–•·→←↑↓×+0-9\s%/.,:;]+", value)


def extract_strings() -> list[str]:
    values: set[str] = set()
    for path in sorted(TEMPLATES.rglob("*.html")):
        source = path.read_text(encoding="utf-8")
        position = 0
        for match in SKIP_BLOCKS.finditer(source):
            chunks = (source[position:match.start()],)
            for chunk in chunks:
                for node in TEXT_NODE.finditer(chunk):
                    value = _normalise(node.group(1))
                    if _is_static(value):
                        values.add(value)
                for attr in UI_ATTR.finditer(chunk):
                    value = _normalise(attr.group(3))
                    if _is_static(value):
                        values.add(value)
            position = match.end()

        tail = source[position:]
        for node in TEXT_NODE.finditer(tail):
            value = _normalise(node.group(1))
            if _is_static(value):
                values.add(value)
        for attr in UI_ATTR.finditer(tail):
            value = _normalise(attr.group(3))
            if _is_static(value):
                values.add(value)

        for block in BLOCK_TITLE.finditer(source):
            value = _normalise(block.group(1))
            if _is_static(value):
                values.add(value)

    return sorted(values)


def existing_for(langue: str) -> dict[str, str]:
    merged: dict[str, str] = {}
    merged.update(TRADUCTIONS.get(langue, {}))
    merged.update(TRADUCTIONS_UI.get(langue, {}))
    merged.update(TRADUCTIONS_UI_COMPLEMENT.get(langue, {}))

    try:
        namespace: dict[str, object] = {}
        exec(compile(GENERATED.read_text(encoding="utf-8"), str(GENERATED), "exec"), namespace)
        generated = namespace.get("TRADUCTIONS_AUTOGEN", {})
        if isinstance(generated, dict):
            merged.update(generated.get(langue, {}))
    except FileNotFoundError:
        pass
    return {str(k): str(v) for k, v in merged.items()}


def load_generated() -> dict[str, dict[str, str]]:
    if not GENERATED.exists():
        return {"en": {}, "mg": {}}
    namespace: dict[str, object] = {}
    exec(compile(GENERATED.read_text(encoding="utf-8"), str(GENERATED), "exec"), namespace)
    value = namespace.get("TRADUCTIONS_AUTOGEN", {})
    if not isinstance(value, dict):
        return {"en": {}, "mg": {}}
    return {
        lang: dict(value.get(lang, {}))
        for lang in ("en", "mg")
        if isinstance(value.get(lang, {}), dict)
    }


def write_generated(catalog: dict[str, dict[str, str]]) -> None:
    content = (
        '"""Chaînes UI générées par scripts/sync_i18n_libretranslate.py.\n\n'
        'Les traductions manuelles restent prioritaires dans app/i18n.py.\n'
        '"""\n'
        "from __future__ import annotations\n\n"
        "TRADUCTIONS_AUTOGEN: dict[str, dict[str, str]] = "
        + pformat(catalog, width=120, sort_dicts=True)
        + "\n"
    )
    GENERATED.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--source", default="fr")
    parser.add_argument("--targets", default="en,mg")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    base_url = (args.url or "").rstrip("/")
    if not base_url:
        import os
        base_url = os.getenv("LIBRETRANSLATE_URL", "").rstrip("/")
    api_key = args.api_key
    if not api_key:
        import os
        api_key = os.getenv("LIBRETRANSLATE_API_KEY", "")

    if not base_url:
        raise SystemExit(
            "LIBRETRANSLATE_URL est requis. Exemple : http://localhost:5000"
        )

    strings = extract_strings()
    catalog = load_generated()

    try:
        languages = supported_languages(base_url=base_url, timeout=args.timeout)
    except LibreTranslateError as exc:
        raise SystemExit(str(exc)) from exc

    targets = [item.strip() for item in args.targets.split(",") if item.strip()]
    for target in targets:
        if target not in languages:
            print(f"[WARN] langue LibreTranslate indisponible: {target}")
            continue

        existing = existing_for(target)
        missing = [value for value in strings if value not in existing and value not in catalog.get(target, {})]
        print(f"[{target}] {len(strings)} chaînes détectées, {len(missing)} manquantes")

        for index, source_text in enumerate(missing, start=1):
            try:
                translated, alternatives = translate_text(
                    source_text,
                    base_url=base_url,
                    source=args.source,
                    target=target,
                    timeout=args.timeout,
                    api_key=api_key,
                    alternatives=2,
                )
            except LibreTranslateError as exc:
                print(f"[WARN] {target}: échec pour {source_text!r}: {exc}")
                continue

            catalog.setdefault(target, {})[source_text] = translated
            alt = f" | alternatives={alternatives!r}" if alternatives else ""
            print(f"  {index}/{len(missing)} {source_text!r} -> {translated!r}{alt}")

    if args.write:
        write_generated(catalog)
        print(f"[OK] catalogue écrit: {GENERATED}")
    else:
        print("[DRY-RUN] rien n'a été écrit. Ajoute --write pour enregistrer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
