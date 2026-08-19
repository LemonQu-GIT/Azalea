"""Lightweight i18n helper for Azalea.

Self-contained on purpose: no Qt import, no dependency on the rest of the
`pet` package, and must never crash even if `configs/config.json` is
missing or malformed (falls back to the default language in that case).

Language resolution order:
    1. `AZALEA_LANG` environment variable (if set) — "zh" or "ja".
    2. Top-level `"language"` key in `configs/config.json`.
    3. Default: "zh".
"""

import json
import os

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_MODULE_DIR, os.pardir))
_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "configs", "config.json")
_LOCALES_DIR = os.path.join(_MODULE_DIR, "locales")

_DEFAULT_LANG = "zh"
_SUPPORTED_LANGS = ("zh", "ja")


def _read_config_language() -> str | None:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return None
    lang = cfg.get("language") if isinstance(cfg, dict) else None
    if isinstance(lang, str) and lang:
        return lang
    return None


def get_language() -> str:
    """Resolve the active UI language. Env var wins over config.json."""
    env_lang = os.environ.get("AZALEA_LANG")
    if env_lang:
        env_lang = env_lang.strip()
        if env_lang in _SUPPORTED_LANGS:
            return env_lang

    cfg_lang = _read_config_language()
    if cfg_lang in _SUPPORTED_LANGS:
        return cfg_lang

    return _DEFAULT_LANG


def _load_catalog(lang: str) -> dict:
    path = os.path.join(_LOCALES_DIR, f"{lang}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


_active_lang = get_language()
_catalog = _load_catalog(_active_lang)
if not _catalog and _active_lang != _DEFAULT_LANG:
    # Fall back to the default language catalog if the resolved one failed to load.
    _catalog = _load_catalog(_DEFAULT_LANG)


def get_catalog() -> dict:
    """Return the full key -> translation mapping for the active language."""
    return _catalog


def t(key: str, **kwargs) -> str:
    """Translate `key`, falling back to `key` itself if missing.

    If `kwargs` are given, applies `str.format(**kwargs)` to the resolved
    string, guarding against format errors by returning the unformatted
    string on failure.
    """
    value = _catalog.get(key, key)
    if not kwargs:
        return value
    try:
        return value.format(**kwargs)
    except Exception:
        return value
