"""Validated, per-provider reasoning and speed preferences."""
from __future__ import annotations

EFFORT_LABELS = {None: "CLI 預設", "low": "輕", "medium": "中", "high": "高",
                 "xhigh": "極高", "max": "最高"}


def validate_options(provider, effort=None, fast=None):
    if effort is not None and (not isinstance(effort, str) or effort not in EFFORT_LABELS) \
            or fast is not None and type(fast) is not bool:
        raise ValueError("思考強度或 Fast 設定無效")
    if provider not in ("codex", "claude") and (effort is not None or fast is not None):
        raise ValueError("此引擎不支援獨立的思考強度與 Fast 設定")
    return {key: value for key, value in {"effort": effort, "fast": fast}.items() if value is not None}


def configured_options(preferences, provider, model):
    saved = preferences.get("translator_options", {})
    models = saved.get(provider, {}) if isinstance(saved, dict) else {}
    options = models.get(model, {}) if isinstance(models, dict) else {}
    if provider not in ("codex", "claude"):
        return {}
    if not isinstance(options, dict):
        options = {}
    try:
        return validate_options(provider, options.get("effort"), options.get("fast", False))
    except ValueError:
        return {"fast": False}


def fingerprint_options(options):
    # Default/off adds no keys, so existing batches keep their fingerprint.
    return {key: value for key, value in options.items() if value is not None and value is not False}


def effective_options(preferences, provider, model):
    options = configured_options(preferences, provider, model)
    if not options:
        return {}
    saved = preferences.get("translator_model_capabilities", {})
    catalog = saved.get(provider, {}) if isinstance(saved, dict) else {}
    caps = catalog.get(model, {}) if isinstance(catalog, dict) else {}
    caps = caps if isinstance(caps, dict) else {}
    return {"effort": options.get("effort") if options.get("effort") in (caps.get("efforts") or []) else None,
            "fast": options.get("fast", False) and caps.get("fast") is True}
