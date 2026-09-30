"""Client minimal pour LibreTranslate.

LibreTranslate est optionnel. Le projet n'appelle jamais un service externe par
defaut : LIBRETRANSLATE_URL doit être explicitement configuré.

Le client est utilisé surtout par scripts/sync_i18n_libretranslate.py afin de
pré-générer les chaînes statiques manquantes puis de les embarquer dans
app/i18n_generated.py. Cela évite une latence réseau à chaque page et protège
les données dynamiques (noms, filières, messages utilisateurs).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class LibreTranslateError(RuntimeError):
    message: str

    def __str__(self) -> str:
        return self.message


def _post_json(
    url: str,
    payload: dict,
    *,
    timeout: float,
    api_key: str = "",
) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "GasyMahay-i18n/1.0",
        },
        method="POST",
    )
    if api_key:
        payload = dict(payload)
        payload["api_key"] = api_key
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "GasyMahay-i18n/1.0",
            },
            method="POST",
        )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:600]
        raise LibreTranslateError(
            f"LibreTranslate HTTP {exc.code}: {detail or exc.reason}"
        ) from exc
    except URLError as exc:
        raise LibreTranslateError(f"LibreTranslate inaccessible: {exc.reason}") from exc
    except TimeoutError as exc:
        raise LibreTranslateError("LibreTranslate timeout") from exc

    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LibreTranslateError("LibreTranslate a renvoyé une réponse JSON invalide.") from exc


def translate_text(
    text: str,
    *,
    base_url: str,
    source: str,
    target: str,
    timeout: float = 8.0,
    api_key: str = "",
    alternatives: int = 0,
) -> tuple[str, list[str]]:
    """Traduit une chaîne courte et retourne (traduction, alternatives)."""
    value = text.strip()
    if not value:
        return text, []
    payload = {
        "q": value,
        "source": source,
        "target": target,
        "format": "text",
    }
    if alternatives > 0:
        payload["alternatives"] = alternatives

    result = _post_json(
        f"{base_url.rstrip('/')}/translate",
        payload,
        timeout=timeout,
        api_key=api_key,
    )
    translated = result.get("translatedText")
    if not isinstance(translated, str) or not translated.strip():
        raise LibreTranslateError("LibreTranslate n'a fourni aucune traduction.")
    alternatives_raw = result.get("alternatives", [])
    alternatives_clean = [
        item.strip()
        for item in alternatives_raw
        if isinstance(item, str) and item.strip()
    ]
    return translated.strip(), alternatives_clean


def supported_languages(
    *,
    base_url: str,
    timeout: float = 8.0,
) -> set[str]:
    request = Request(
        f"{base_url.rstrip('/')}/languages",
        headers={"Accept": "application/json", "User-Agent": "GasyMahay-i18n/1.0"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise LibreTranslateError(f"Impossible de lire les langues LibreTranslate: {exc}") from exc

    result: set[str] = set()
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("code"), str):
                result.add(item["code"])
    return result
