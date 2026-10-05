from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path

SUPPORTED_LOCALES = ("en", "id")
DEFAULT_LOCALE = "en"

@lru_cache(maxsize=8)
def load_locale(locale: str) -> dict[str, str]:
    path = Path(__file__).parent / "locales" / f"{locale}.json"
    if not path.exists():
        locale = DEFAULT_LOCALE
        path = Path(__file__).parent / "locales" / f"{locale}.json"
    return json.loads(path.read_text(encoding="utf-8"))

def normalize_locale(value: str | None) -> str:
    if not value:
        return DEFAULT_LOCALE
    candidate = value.strip().lower().replace("_", "-").split("-")[0]
    return candidate if candidate in SUPPORTED_LOCALES else DEFAULT_LOCALE

def browser_locale(header: str | None) -> str:
    if not header:
        return DEFAULT_LOCALE
    for item in header.split(","):
        locale = normalize_locale(item.split(";")[0])
        if locale in SUPPORTED_LOCALES:
            return locale
    return DEFAULT_LOCALE

def translate(locale: str, key: str, **values: object) -> str:
    text = load_locale(normalize_locale(locale)).get(key)
    if text is None:
        text = load_locale(DEFAULT_LOCALE).get(key, key)
    return text.format(**values)
